import platform
import threading
import multiprocessing
import os

def set_high_priority():
    """Establecer alta prioridad para el proceso/hilo actual"""
    try:
        if platform.system() == "Windows":
            try:
                import win32api
                import win32process
                import win32con
                # Establecer alta prioridad en Windows
                pid = win32api.GetCurrentProcessId()
                handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
                win32process.SetPriorityClass(handle, win32process.HIGH_PRIORITY_CLASS)
                return True
            except ImportError:
                # Si no está disponible pywin32, intentar con psutil
                try:
                    import psutil
                    process = psutil.Process()
                    process.nice(psutil.HIGH_PRIORITY_CLASS)
                    return True
                except ImportError:
                    pass
        elif hasattr(os, 'nice'):
            os.nice(-5)  # Aumentar prioridad en sistemas Unix
            return True
    except:
        pass
    return False

def create_high_priority_thread(target, *args, **kwargs):
    """Crear un hilo con alta prioridad"""
    # Separar argumentos del hilo de argumentos de la función objetivo
    thread_kwargs = {}
    target_kwargs = {}
    
    # Argumentos específicos del hilo
    thread_kwargs['daemon'] = False
    
    # Argumentos para la función objetivo (excluir argumentos del hilo)
    for key, value in kwargs.items():
        if key not in ['daemon']:
            target_kwargs[key] = value
    
    # Crear función wrapper con alta prioridad
    def high_priority_target():
        set_high_priority()
        return target(*args, **target_kwargs)
    
    thread = threading.Thread(target=high_priority_target, **thread_kwargs)
    return thread

def create_high_priority_process(target, *args, **kwargs):
    """Crear un proceso con alta prioridad"""
    # Para multiprocessing, es mejor establecer la prioridad dentro de la función objetivo
    # para evitar problemas de serialización
    process = multiprocessing.Process(target=target, args=args, kwargs=kwargs, daemon=False)
    return process

def is_windows():
    """Verificar si estamos en Windows"""
    return platform.system() == "Windows"

def is_linux():
    """Verificar si estamos en Linux"""
    return platform.system() == "Linux"

def is_macos():
    """Verificar si estamos en macOS"""
    return platform.system() == "Darwin" 