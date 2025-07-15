import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Qt
import sounddevice as sd
from audio.audio import MicrophoneListener
from window.window import CreateWindow
from client.client import Client
from threading import Thread
import multiprocessing
import platform
from utils.thread_utils import create_high_priority_thread, set_high_priority

UI_FILE = "./src/ui/main.ui"

class MyMainWindow(CreateWindow):
    def __init__(self):
        super().__init__(UI_FILE)
        self.listener_thread = None
        self.microphone_listener = None
        self.setup_ui()
        self.listar_dispositivos()
        self.client = Client("http://127.0.0.1:3500", self.process_audio_data)

        # Configurar la ventana para mantener el procesamiento en segundo plano
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, False)
        
        # Configurar la aplicación para mantener hilos activos al minimizar
        if platform.system() == "Windows":
            # En Windows, configurar para mantener hilos activos
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Ejecutar el cliente SocketIO en un hilo de alta prioridad
        self.client_thread = create_high_priority_thread(target=self.client.run_socketio_client)
        self.client_thread.start()

    def listar_dispositivos(self):
        print("\nDispositivos disponibles:")
        dispositivos = sd.query_devices()
        for i, d in enumerate(dispositivos):
            tipo = "Entrada/Salida"
            if d.get('max_input_channels', 0) > 0 and d.get('max_output_channels', 0) > 0:
                tipo = "Entrada/Salida"
            elif d.get('max_input_channels', 0) > 0:
                tipo = "Entrada"
            elif d.get('max_output_channels', 0) > 0:
                tipo = "Salida"
            print(f"{i}: {d.get('name', 'Unknown')} ({tipo})")

    def setup_ui(self):
        if hasattr(self.ui_widget, 'btn_mute'):
            self.ui_widget.btn_mute.clicked.connect(self.start_and_stop_listening)

    def set_monitor_volume(self, value):
        """Cambiar volumen de monitoreo (0-100)"""
        if self.microphone_listener:
            self.microphone_listener.set_monitor_gain(value / 100.0)

    def start_and_stop_listening(self):
        if self.microphone_listener and self.microphone_listener.is_running():
            self.stop_listening()
            if hasattr(self.ui_widget, 'btn_mute'):
                self.ui_widget.btn_mute.setText("Iniciar micrófono")
            return

        if hasattr(self.ui_widget, 'btn_mute'):
            self.ui_widget.btn_mute.setText("Silenciar")

        # Seleccionar dispositivos (ajusta estos índices/nombres según tu sistema)
        input_device = "Micrófono (WO Mic Device), MME"
        output_device = "Auriculares (2- TWS), MME"
        
        # Crear MicrophoneListener con callback de error
        self.microphone_listener = MicrophoneListener(
            samplerate=44100,
            channels=1,
            blocksize_ms=40,  # Aumentar para reducir overflow/underflow
            input_device=input_device,
            output_device=output_device,
            monitor_gain=0.7,  # Volumen inicial
            send_package=self.client.send_package,
            on_error=self._handle_audio_error
        )
        
        # Usar threading.Thread con alta prioridad para el audio
        self.listener_thread = create_high_priority_thread(target=self.microphone_listener.run)
        self.listener_thread.start()

    def _handle_audio_error(self, error_msg):
        print(f"Error de audio: {error_msg}")
        self.stop_listening()

    def stop_listening(self):
        if self.microphone_listener:
            self.microphone_listener.stop()
            if hasattr(self.ui_widget, 'btn_mute'):
                self.ui_widget.btn_mute.setText("Iniciar micrófono")

    def process_audio_data(self, data):
        if self.microphone_listener and hasattr(self.microphone_listener, 'audio_queue_put'):
            self.microphone_listener.audio_queue_put(data)

    def changeEvent(self, event):
        """Manejar cambios de estado de la ventana (minimizar, restaurar, etc.)"""
        if event.type() == event.Type.WindowStateChange:
            # Cuando la ventana cambia de estado, asegurar que los hilos sigan activos
            set_high_priority()
        super().changeEvent(event)

    def closeEvent(self, event):
        """Manejar el cierre de la ventana"""
        self.stop_listening()
        if self.client:
            self.client.stop()
        event.accept()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    
    # Configurar la aplicación para mantener el procesamiento en segundo plano
    app.setQuitOnLastWindowClosed(True)
    
    # Configurar la aplicación para mantener hilos activos al minimizar
    if platform.system() == "Windows":
        # En Windows, configurar para mantener hilos activos
        app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    
    window = MyMainWindow()
    window.show()
    sys.exit(app.exec())