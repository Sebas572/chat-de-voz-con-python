import sys
import sounddevice as sd
import numpy as np
from PySide6.QtCore import QObject, Signal, QThread
import queue
import threading
import time
import platform
import os
import time
from utils.thread_utils import set_high_priority

class MicrophoneListener:
    def __init__(self, samplerate=44100, channels=1, blocksize_ms=50, 
                 input_device=None, output_device=None, monitor_gain=0.8, send_package=None, on_error=None, on_start=None, on_stop=None):
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = int(samplerate * (blocksize_ms / 1000.0))
        self.input_device = input_device
        self.output_device = output_device
        self.monitor_gain = monitor_gain  # Volumen del monitoreo (0.0 a 1.0)
        self._running = False
        self.audio_queue = queue.Queue(maxsize=200)  # Aumentar tamaño para reducir underflow
        self.latency = 'low'  # Para reducir la latencia
        self.send_package = send_package  # Función para enviar datos al servidor
        self.on_error = on_error
        self.on_start = on_start
        self.on_stop = on_stop
        self._input_stream = None
        self._output_stream = None
        self._lock = threading.Lock()  # Para sincronización
        self._last_output_time = 0  # Para sincronización de salida

    def _input_callback(self, indata, frames, pa_time, status):
        """Callback para captura de micrófono"""
        if status:
            # Solo mostrar overflow ocasionalmente para no saturar la consola
            current_time = time.time()
            if current_time - self._last_output_time > 1.0:  # Mostrar máximo una vez por segundo
                print(f"Input status: {status}", file=sys.stderr)
                self._last_output_time = current_time

        try:
            # Enviar datos para procesamiento
            if self.send_package:
                self.send_package({"data": indata.copy()})
        except Exception as e:
            if self.on_error:
                self.on_error(f"Error en input callback: {e}")
    
    def audio_queue_put(self, indata):
        """Agregar datos de audio a la cola de monitoreo"""
        try:
            # Si la cola está llena, eliminar el elemento más antiguo
            if self.audio_queue.full():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
            
            # Agregar los nuevos datos con el volumen aplicado
            with self._lock:
                gain = self.monitor_gain
            
            # Aplicar ganancia y asegurar que no hay clipping
            audio_data = indata.copy() * gain
            audio_data = np.clip(audio_data, -1.0, 1.0)  # Evitar clipping
            
            self.audio_queue.put(audio_data, block=False)
        except Exception as e:
            print(f"Error en audio_queue_put: {e}")

    def _output_callback(self, outdata, frames, pa_time, status):
        """Callback para salida de audio (monitoreo)"""
        if status:
            print(f"Output status: {status}", file=sys.stderr)
        
        try:
            # Obtener datos de la cola para monitoreo
            data = self.audio_queue.get_nowait()
            if len(data) < len(outdata):
                outdata[:len(data)] = data
                outdata[len(data):] = 0  # Llenar con silencio
            else:
                outdata[:] = data[:len(outdata)]
        except queue.Empty:
            # Si no hay datos, llenar con silencio
            outdata.fill(0)
            # Solo mostrar underflow ocasionalmente para no saturar la consola
            current_time = time.time()
            if current_time - self._last_output_time > 1.0:  # Mostrar máximo una vez por segundo
                self._last_output_time = current_time

    def run(self):
        """Ejecutar el listener de micrófono en un hilo de alta prioridad"""
        self._running = True
        
        # Configurar la prioridad del hilo actual
        set_high_priority()
        
        # Inicializar tiempo para control de mensajes
        self._last_output_time = time.time()
        
        try:
            # Obtener información de dispositivos
            try:
                input_device_info = sd.query_devices(self.input_device) if self.input_device else None
                output_device_info = sd.query_devices(self.output_device) if self.output_device else None
                input_name = str(input_device_info) if input_device_info else "default"
                output_name = str(output_device_info) if output_device_info else "default"
            except:
                input_name = "default"
                output_name = "default"
            print(f"Input: {input_name}, Output: {output_name}")

            # Crear stream de entrada con configuración optimizada
            self._input_stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                callback=self._input_callback,
                blocksize=self.blocksize,
                device=self.input_device,
                latency='low',
                dtype=np.float32,
                clip_off=False,  # Evitar clipping
                dither_off=True   # Reducir ruido
            )
            
            # Crear stream de salida para monitoreo con configuración optimizada
            self._output_stream = sd.OutputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                callback=self._output_callback,
                blocksize=self.blocksize,
                device=self.output_device,
                latency='low',
                dtype=np.float32,
                clip_off=False,  # Evitar clipping
                dither_off=True   # Reducir ruido
            )
            
            print("Iniciando grabación y monitoreo...")
            self._input_stream.start()
            self._output_stream.start()
            
            if self.on_start:
                self.on_start()

            # Bucle principal con menor latencia
            while self._running:
                time.sleep(0.001)  # 1ms de latencia en lugar de 10ms
            
        except Exception as e:
            error_msg = f"Error en MicrophoneListener: {e}"
            print(error_msg, file=sys.stderr)
            if self.on_error:
                self.on_error(error_msg)
        finally:
            self.stop()

    def stop(self):
        """Detener el listener de micrófono"""
        if self._running:
            self._running = False
            
            # Detener streams de audio
            if self._input_stream:
                try:
                    self._input_stream.stop()
                    self._input_stream.close()
                except:
                    pass
                self._input_stream = None
                
            if self._output_stream:
                try:
                    self._output_stream.stop()
                    self._output_stream.close()
                except:
                    pass
                self._output_stream = None
            
            # Limpiar la cola de audio
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
            
            if self.on_stop:
                self.on_stop()

    def is_running(self):
        """Verificar si el listener está ejecutándose"""
        return self._running

    def set_monitor_gain(self, gain):
        """Ajustar el volumen del monitoreo de forma thread-safe"""
        with self._lock:
            self.monitor_gain = max(0.0, min(1.0, gain))