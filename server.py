
# Nuevo servidor Socket.IO compatible con el cliente
import socketio
import eventlet
import numpy as np

sio = socketio.Server()
app = socketio.WSGIApp(sio)

@sio.event
def connect(sid, environ):
	print(f"Client connected: {sid}")

@sio.event
def disconnect(sid):
	print(f"Client disconnected: {sid}")

@sio.event
def voice(sid, data):
	print(f"Received 'voice' event from {sid}. Data type: {type(data)}")
	# Aquí podrías procesar el audio, reenviarlo, etc.
	# Ejemplo: reenviar el audio a todos los clientes conectados
	sio.emit('voice', data)

@sio.event
def chat_message(sid, msg):
    print(f"Mensaje de chat de {sid}: {msg}")
    sio.emit('chat_message', msg)

if __name__ == "__main__":
	print("Socket.IO server listening on http://localhost:3000 ...")
	eventlet.wsgi.server(eventlet.listen(('localhost', 3500)), app)