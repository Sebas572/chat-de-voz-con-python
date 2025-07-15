import sounddevice as sd

# Listar todos los dispositivos de audio
dispositivos = sd.query_devices()
print("Dispositivos de audio disponibles:")
for i, dispositivo in enumerate(dispositivos):
    print(f"{i}: [{dispositivo['name']}] (Entradas: {dispositivo['max_input_channels']})")

# Obtener dispositivo de entrada predeterminado
# dispositivo_predeterminado = sd.default.device[0]  # Índice del dispositivo de entrada
# print(f"\nDispositivo de entrada predeterminado: {dispositivos[dispositivo_predeterminado]['name']}")