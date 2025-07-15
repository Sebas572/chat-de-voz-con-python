import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice

class CreateWindow(QWidget):
	UI_FILE: str = None
	ui_widget = None

	def __init__(self, path_ui):
		super().__init__()
		self.UI_FILE = path_ui
		self.load_ui()

	def load_ui(self):
		loader = QUiLoader()
		ui_file = QFile(self.UI_FILE)
		if not ui_file.open(QIODevice.ReadOnly):
			print(f"No se pudo abrir el archivo UI: {ui_file.errorString()}")
			sys.exit(-1)
		
		self.ui_widget = loader.load(ui_file) # Load the UI as a separate widget
		ui_file.close()

		if not self.ui_widget:
			print("Error al cargar la interfaz de usuario.")
			sys.exit(-1)

		# Create a layout for MyMainWindow
		main_layout = QVBoxLayout(self) # Set 'self' as the parent for the layout
		main_layout.addWidget(self.ui_widget) # Add the loaded UI widget to this layout

		# Set the window title from the loaded UI (if the UI is a QWidget/QMainWindow)
		self.setWindowTitle(self.ui_widget.windowTitle() if hasattr(self.ui_widget, 'windowTitle') else "Default Title")

		ui_size = self.ui_widget.sizeHint() 
		self.setFixedSize(ui_size) # Establece el tamaño de la ventana principal para que sea fijo y igual al tamaño del UI