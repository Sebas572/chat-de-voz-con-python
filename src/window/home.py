import sys
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel, QMessageBox, QSizePolicy, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal
import sounddevice as sd
from audio.audio import MicrophoneListener
from window.window import CreateWindow
from client.client import Client
import multiprocessing
import platform
from utils.thread_utils import create_high_priority_thread, set_high_priority

UI_FILE = "./src/ui/main.ui"

class MyMainWindow(CreateWindow):
    chat_message_signal = Signal(str)
    new_user_signal = Signal(str)
    remove_user_signal = Signal(str)

    def __init__(self):
        super().__init__(UI_FILE)
        self.listener_thread = None
        self.microphone_listener = None
        self.setup_ui()
        dispositivos = self.listar_dispositivos()
        dispositivos_entrada = [(index, name) for name, index in dispositivos["input"].items()]
        print(dispositivos_entrada)

        if not dispositivos_entrada:
            QMessageBox.critical(None, "Error", "No se encontraron dispositivos de entrada de audio.")
            sys.exit()

        mic_names = [d[1] for d in dispositivos_entrada]
        mic_choice, ok = QInputDialog.getItem(None, "Seleccionar micrófono", "Elige el micrófono de entrada:", mic_names, 0, False)
        if not ok:
            QMessageBox.information(None, "Cancelado", "Se requiere seleccionar un micrófono.")
            sys.exit()
        self.input_device = dispositivos_entrada[mic_names.index(mic_choice)][0]

        # Selección de salida de audio
        dispositivos_salida = [(index, name) for name, index in dispositivos["output"].items()]
        if not dispositivos_salida:
            QMessageBox.critical(None, "Error", "No se encontraron dispositivos de salida de audio.")
            sys.exit()
        out_names = [d[1] for d in dispositivos_salida]
        out_choice, ok = QInputDialog.getItem(None, "Seleccionar salida de audio", "Elige el dispositivo de salida:", out_names, 0, False)
        if not ok:
            QMessageBox.information(None, "Cancelado", "Se requiere seleccionar una salida de audio.")
            sys.exit()
        self.output_device = dispositivos_salida[out_names.index(out_choice)][0]

        self.name, ok = QInputDialog.getText(None, "Name", "Write your name:")
        if not ok:
            QMessageBox.information(
                None,
                "Sorry",
                "I need your name"
            )
            sys.exit()
            
        self.code, ok = QInputDialog.getText(None, "Room", "Room code:")
        if not ok:
            QMessageBox.information(
                None,
                "Sorry",
                "I need room code"
            )
            sys.exit()

        self.client = Client(
            url="http://127.0.0.1:3500",
            callback_play_sound=self.process_audio_data,
            callback_chat_message=self.receive_chat_message,
            callback_users_online=self.receive_users_online,
            callback_remove_user=self.receive_remove_user,
            name=self.name,
            room_code=self.code,
        )

        self.ui_widget.label_room.setText(self.code)

        # --- Chat scrollable area setup ---
        self.chat_scroll_area = self.ui_widget.chat

        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch(1)  # Para empujar mensajes hacia arriba
        self.chat_container.setLayout(self.chat_layout)
        self.chat_scroll_area.setWidget(self.chat_container)

        self.name_scroll_area = self.ui_widget.scroll_area_connect
        self.name_scroll_area.setWidgetResizable(True)
        self.name_container = QWidget()
        self.name_layout = QVBoxLayout(self.name_container)
        self.name_layout.setSpacing(8)
        self.name_layout.addStretch(1)  # Para empujar mensajes hacia arriba
        self.name_container.setLayout(self.name_layout)
        self.name_scroll_area.setWidget(self.name_container)
        # --- End chat scrollable area setup ---

        # Configurar la ventana para mantener el procesamiento en segundo plano
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, False)
        
        if platform.system() == "Windows":
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        self.client_thread = create_high_priority_thread(target=self.client.run_socketio_client)
        self.client_thread.start()

        self.chat_message_signal.connect(self._add_chat_message)
        self.new_user_signal.connect(self._add_new_user)
        self.remove_user_signal.connect(self._remove_user)

    def listar_dispositivos(self):
        print("\nDispositivos disponibles:")
        dispositivos = sd.query_devices()
        list_dispositivos = {"input": {}, "output": {}}

        for i, d in enumerate(dispositivos):
            tipo = "input/output"
            if d.get('max_input_channels', 0) > 0 and d.get('max_output_channels', 0) > 0:
                tipo = "input/output"
            elif d.get('max_input_channels', 0) > 0:
                tipo = "input"
            elif d.get('max_output_channels', 0) > 0:
                tipo = "output"
            name = d.get('name', 'Unknown')
            if name == 'Unknown':
                pass

            if tipo == "input/output":
                list_dispositivos["input"][name] = i
                list_dispositivos["output"][name] = i
            else:
                list_dispositivos[tipo][name] = i

        return list_dispositivos

    def setup_ui(self):
        if hasattr(self.ui_widget, 'btn_mute'):
            self.ui_widget.btn_mute.clicked.connect(self.start_and_stop_listening)
        if hasattr(self.ui_widget, 'btn_send_msg'):
            self.ui_widget.btn_send_msg.clicked.connect(self.send_chat_message)

    def send_chat_message(self):
        if hasattr(self.ui_widget, 'textEdit'):
            text = self.ui_widget.textEdit.toPlainText().strip()
            if text:
                self.client.send_chat_message(text)
                self.ui_widget.textEdit.clear()

    def receive_chat_message(self, msg):
        self.chat_message_signal.emit(msg)

    def receive_users_online(self, name):
        self.new_user_signal.emit(name)

    def receive_remove_user(self, name):
        self.remove_user_signal.emit(name)

    def _add_chat_message(self, msg):
        label = QLabel(msg)
        label.setWordWrap(True)
        label.setMinimumHeight(36)  # Altura mínima para simular burbuja de chat
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        label.setStyleSheet("""
            background: #000000;
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 4px;
        """)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, label)

        # Scroll automático al final
        if self.chat_scroll_area is not None:
            self.chat_scroll_area.verticalScrollBar().setValue(
                self.chat_scroll_area.verticalScrollBar().maximum()
            )
    
    def _add_new_user(self, name):
        if not hasattr(self, 'user_labels'):
            self.user_labels = {}
        
        if name in self.user_labels:
            return
        
        # Crear nuevo label solo si no existe
        label = QLabel(name)
        label.setWordWrap(True)
        label.setMinimumHeight(36)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        label.setStyleSheet("""
            color: #000000;
            background: #fff;
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 4px;
        """)
        
        # Guardar referencia
        self.user_labels[name] = label
        
        # Añadir al layout
        self.name_layout.insertWidget(self.name_layout.count() - 1, label)

    def _remove_user(self, name):
        if hasattr(self, 'user_labels') and name in self.user_labels:
            label = self.user_labels[name]
            self.name_layout.removeWidget(label)
            label.deleteLater()
            del self.user_labels[name]

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

        # Usar los dispositivos seleccionados por el usuario
        input_device = self.input_device
        output_device = self.output_device
        
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

def start_home():
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