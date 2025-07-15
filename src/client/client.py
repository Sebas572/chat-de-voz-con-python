from time import sleep
import socketio
import multiprocessing
import numpy as np
import threading
from queue import Empty
import os
import platform
from utils.thread_utils import set_high_priority, create_high_priority_thread, create_high_priority_process

# Función de nivel superior para el proceso hijo
def run_client_process(url, send_queue, receive_queue):
    """Función ejecutada en el proceso hijo con alta prioridad"""
    # Configurar alta prioridad para el proceso hijo
    set_high_priority()
    
    sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=1)
    
    # Definimos los callbacks internos
    def on_connect():
        print('Connection established with Socket.IO server!')

    def on_disconnect():
        print('Disconnected from Socket.IO server.')

    def on_connect_error(data):
        print(f'The connection failed! Data: {data}')

    def on_voice_data(data):
        if isinstance(data, list):
            receive_queue.put(data)

    # Asignamos los callbacks
    sio.on('connect', on_connect)
    sio.on('disconnect', on_disconnect)
    sio.on('connect_error', on_connect_error)
    sio.on('voice', on_voice_data)
    
    # Evento para controlar el hilo de envío
    stop_event = threading.Event()
    
    def sender_thread():
        """Hilo que envía datos desde la cola con alta prioridad"""
        # Configurar alta prioridad para el hilo de envío
        set_high_priority()
            
        while not stop_event.is_set():
            try:
                # Intentar obtener datos de la cola con timeout corto
                package = send_queue.get(timeout=0.01)  # 10ms timeout para menor latencia
                if sio.connected:
                    # Accedemos directamente a los datos sin subniveles adicionales
                    data_to_send = package["data"]["data"]
                    if isinstance(data_to_send, np.ndarray):
                        data_to_send = data_to_send.tolist()
                    sio.emit('voice', data_to_send)
            except Empty:
                pass
            except Exception as e:
                print(f"Error en sender_thread: {e}")
    
    # Iniciar hilo de envío
    sender = threading.Thread(target=sender_thread, daemon=False)
    sender.start()
    
    # Bucle de conexión/reconexión
    while not stop_event.is_set():
        try:
            sio.connect(url)
            sio.wait()
        except (ConnectionRefusedError, Exception) as e:
            print(f"Connection error: {e}")
        sleep(1)
    
    # Limpiar al terminar
    stop_event.set()
    sender.join(timeout=1.0)
    if sio.connected:
        sio.disconnect()

class Client():
    def __init__(self, url='http://localhost:3000', callback_play_sound=None):
        self.url = url
        self.callback_play_sound = callback_play_sound
        self.connected = False
        self._process = None
        # Cola para enviar datos al proceso hijo
        self.send_queue = multiprocessing.Queue(maxsize=1000)  # Limitar tamaño para evitar memoria excesiva
        # Cola para recibir datos del proceso hijo
        self.receive_queue = multiprocessing.Queue(maxsize=1000)
        # Evento para detener el hilo de recepción
        self.stop_event = threading.Event()
        # Hilo para recibir datos
        self.receive_thread = None
                
    def run_socketio_client(self):
        """Inicia el cliente Socket.IO en un proceso separado con alta prioridad"""
        if self._process is None or not self._process.is_alive():
            self._process = multiprocessing.Process(
                target=run_client_process,
                args=(self.url, self.send_queue, self.receive_queue),
                daemon=False  # Evitar que se termine al minimizar
            )
            self._process.start()
            
            # Iniciar hilo de recepción en el proceso principal con alta prioridad
            self.stop_event.clear()
            self.receive_thread = create_high_priority_thread(target=self._receive_loop)
            self.receive_thread.start()

    def _receive_loop(self):
        """Bucle para recibir datos en el proceso principal con alta prioridad"""
        # Configurar alta prioridad para el hilo de recepción
        set_high_priority()
            
        while not self.stop_event.is_set():
            try:
                # Bloquear hasta que haya datos disponibles con timeout corto
                data_list = self.receive_queue.get(timeout=0.01)  # 10ms timeout para menor latencia
                if self.callback_play_sound:
                    arr = np.array(data_list, dtype=np.float32)
                    self.callback_play_sound(arr)
            except Empty:
                pass
            except Exception as e:
                print(f"Error en receive_loop: {e}")

    def stop(self):
        """Detiene el cliente y los hilos asociados"""
        self.stop_event.set()
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join()

    def send_package(self, data):
        """Envía datos de audio al proceso de Socket.IO mediante la cola"""
        try:
            # Si la cola está llena, eliminar el elemento más antiguo
            if self.send_queue.full():
                try:
                    self.send_queue.get_nowait()
                except Empty:
                    pass
            
            # Mantenemos los datos como están (se convertirán en el proceso hijo)
            self.send_queue.put({'data': data}, block=False)
        except Exception as e:
            print(f"Error en send_package: {e}")