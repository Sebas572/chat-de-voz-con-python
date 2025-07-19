from time import sleep
from PySide6.QtCore import Signal
import socketio
import multiprocessing
import numpy as np
import threading
from queue import Empty
from utils.thread_utils import (
    set_high_priority,
    create_high_priority_thread,
)

# Función de nivel superior para el proceso hijo
def run_client_process(
    url,
    room_code,
    send_queue,
    receive_queue,
    chat_send_queue,
    chat_receive_queue,
    users_receive_queue,
    name,
):

    """Función ejecutada en el proceso hijo con alta prioridad"""
    # Configurar alta prioridad para el proceso hijo
    set_high_priority()

    sio = socketio.Client(
        reconnection=True, reconnection_attempts=0, reconnection_delay=1
    )

    # Definimos los callbacks internos
    def on_connect():
        print("Connection established with Socket.IO server!")

        sleep(5)
        sio.emit("new_user", {"name": name, "room_code": room_code})

    def on_disconnect():
        print("Disconnected from Socket.IO server.")

    def on_connect_error(data):
        print(f"The connection failed! Data: {data}")

    def on_voice_data(data):
        if isinstance(data, list):
            receive_queue.put(data)

    def on_chat_message(msg):
        chat_receive_queue.put(msg)

    def on_new_user(name):
        users_receive_queue.put({"name": name, "join": True})

    def on_disconnect_user(name):
        users_receive_queue.put({"name": name, "join": False})

    # Asignamos los callbacks
    sio.on("connect", on_connect)
    sio.on("disconnect", on_disconnect)
    sio.on("connect_error", on_connect_error)
    sio.on("voice", on_voice_data)
    sio.on("new_user", on_new_user)
    sio.on("disconnect_user", on_disconnect_user)
    sio.on("chat_message", on_chat_message)

    # Evento para controlar el hilo de envío
    stop_event = threading.Event()

    def sender_thread():
        """Hilo que envía datos desde la cola con alta prioridad"""
        # Configurar alta prioridad para el hilo de envío
        set_high_priority()

        while not stop_event.is_set():
            try:
                # Intentar obtener datos de la cola con timeout corto
                package = send_queue.get(
                    timeout=0.01
                )  # 10ms timeout para menor latencia
                if sio.connected:
                    # Accedemos directamente a los datos sin subniveles adicionales
                    data_to_send = package["data"]["data"]
                    if isinstance(data_to_send, np.ndarray):
                        data_to_send = data_to_send.tolist()
                    sio.emit("voice", data_to_send)
            except Empty:
                pass
            except Exception as e:
                print(f"Error en sender_thread: {e}")

    def chat_sender_thread():
        """Hilo que envía mensajes de chat desde la cola con alta prioridad"""
        set_high_priority()
        while not stop_event.is_set():
            try:
                msg = chat_send_queue.get(
                    timeout=0.05
                )  # 50ms timeout para mensajes de chat
                if sio.connected:
                    sio.emit("chat_message", msg)
            except Empty:
                pass
            except Exception as e:
                print(f"Error en chat_sender_thread: {e}")

    def disconnect():
        print("Disconnected")

        stop_event.set()
        sender.join(timeout=1.0)
        chat_sender.join(timeout=1.0)
        if sio.connected:
            sio.disconnect()

    # Iniciar hilo de envío
    sender = threading.Thread(target=sender_thread, daemon=False)
    chat_sender = threading.Thread(target=chat_sender_thread, daemon=False)
    sender.start()
    chat_sender.start()

    # Bucle de conexión/reconexión
    while not stop_event.is_set():
        try:
            print(f"Intentando conectar a {url} usando websocket...")
            sio.connect(url, transports=['websocket'])
            print("Conexión websocket exitosa!")
            sio.wait()
        except Exception as e:
            print(f"Fallo la conexión websocket: {e}")
            print("Intentando fallback a polling...")
            try:
                sio.connect(url, transports=['polling'])
                print("Conexión polling exitosa!")
                sio.wait()
            except Exception as e2:
                print(f"Fallo la conexión polling: {e2}")
        sleep(1)
    # Limpiar al terminar
    disconnect()


class Client:
    def __init__(
        self,
        url="http://localhost:3500",
        callback_play_sound=None,
        callback_chat_message=None,
        callback_users_online=None,
        callback_remove_user=None,
        name=None,
        room_code=None,
    ):
        self.url = url
        self.room_code = room_code
        self.callback_play_sound = callback_play_sound
        self.callback_chat_message = callback_chat_message
        self.callback_users_online = callback_users_online
        self.callback_remove_user = callback_remove_user
        self.connected = False
        self._process = None
        # Cola para enviar datos al proceso hijo
        self.send_queue = multiprocessing.Queue(
            maxsize=1000
        )  # Limitar tamaño para evitar memoria excesiva
        # Cola para recibir datos del proceso hijo
        self.receive_queue = multiprocessing.Queue(maxsize=1000)
        self.chat_send_queue = multiprocessing.Queue(maxsize=100)
        self.chat_receive_queue = multiprocessing.Queue(maxsize=100)
        self.users_receive_queue = multiprocessing.Queue(maxsize=100)

        # Evento para detener el hilo de recepción
        self.stop_event = threading.Event()
        # Hilo para recibir datos
        self.receive_thread = None
        self.chat_receive_thread = None
        self.name = name

    def run_socketio_client(self):
        """Inicia el cliente Socket.IO en un proceso separado con alta prioridad"""
        if self._process is None or not self._process.is_alive():
            self._process = multiprocessing.Process(
                target=run_client_process,
                args=(
                    self.url,
                    self.room_code,
                    self.send_queue,
                    self.receive_queue,
                    self.chat_send_queue,
                    self.chat_receive_queue,
                    self.users_receive_queue,
                    self.name
                ),
                daemon=False,  # Evitar que se termine al minimizar
            )
            self._process.start()

            # Iniciar hilo de recepción en el proceso principal con alta prioridad
            self.stop_event.clear()
            self.receive_thread = create_high_priority_thread(target=self._receive_loop)
            self.receive_thread.start()
            self.chat_receive_thread = create_high_priority_thread(
                target=self._chat_receive_loop
            )
            self.chat_receive_thread.start()
            self.online_users_thread = create_high_priority_thread(
                target=self._receive_name_loop
            )
            self.online_users_thread.start()

    def _receive_loop(self):
        """Bucle para recibir datos en el proceso principal con alta prioridad"""
        # Configurar alta prioridad para el hilo de recepción
        set_high_priority()

        while not self.stop_event.is_set():
            try:
                # Bloquear hasta que haya datos disponibles con timeout corto
                data_list = self.receive_queue.get(
                    timeout=0.01
                )  # 10ms timeout para menor latencia
                if self.callback_play_sound:
                    arr = np.array(data_list, dtype=np.float32)
                    self.callback_play_sound(arr)
            except Empty:
                pass
            except Exception as e:
                print(f"Error en receive_loop: {e}")

    def _receive_name_loop(self):
        set_high_priority()

        while not self.stop_event.is_set():
            try:
                user = self.users_receive_queue.get(timeout=0.05)
                if self.callback_users_online and self.callback_remove_user:
                    if user["join"]:
                        self.callback_users_online(user["name"])
                    else:
                        self.callback_remove_user(user["name"])
            except Empty:
                pass
            except Exception as e:
                print(f"Error en chat_receive_loop: {e}")

    def _chat_receive_loop(self):
        """Bucle para recibir mensajes de chat en el proceso principal con alta prioridad"""
        set_high_priority()
        while not self.stop_event.is_set():
            try:
                msg = self.chat_receive_queue.get(
                    timeout=0.05
                )  # 50ms timeout para mensajes de chat
                if self.callback_chat_message:
                    self.callback_chat_message(msg)
            except Empty:
                pass
            except Exception as e:
                print(f"Error en chat_receive_loop: {e}")

    def stop(self):
        """Detiene el cliente y los hilos asociados"""
        self.stop_event.set()
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
        if self.chat_receive_thread and self.chat_receive_thread.is_alive():
            self.chat_receive_thread.join(timeout=1.0)
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
            self.send_queue.put({"data": data}, block=False)
        except Exception as e:
            print(f"Error en send_package: {e}")

    def send_chat_message(self, msg):
        """Envía mensajes de chat al proceso de Socket.IO mediante la cola"""
        try:
            if self.chat_send_queue.full():
                try:
                    self.chat_send_queue.get_nowait()
                except Empty:
                    pass
            self.chat_send_queue.put(f"{self.name}: {msg}", block=False)
        except Exception as e:
            print(f"Error en send_chat_message: {e}")
