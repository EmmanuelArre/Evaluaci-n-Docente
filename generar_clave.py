"""Genera una clave Fernet para CLAVE_CIFRADO_ACCESO.

Uso:   python generar_clave.py
Copia la línea que imprime al archivo .env (nunca la subas a GitHub ni la incluyas en el ZIP).
IMPORTANTE: si pierdes esta clave, las contraseñas de los grupos ya guardadas no se pueden recuperar
(habría que asignarlas de nuevo desde el panel). Guarda una copia en un lugar seguro.
"""
from cryptography.fernet import Fernet

print("CLAVE_CIFRADO_ACCESO=" + Fernet.generate_key().decode())
