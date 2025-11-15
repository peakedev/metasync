import os
import keyring

def get_secret(env_var_name: str, keyring_service: str, keyring_username: str, local: bool = True):

    secret_value = os.getenv(env_var_name)
    if not secret_value:
        secret_value = keyring.get_password(keyring_service, keyring_username)
        if not secret_value:
            raise ValueError(f"Secret not found in environment variable '{env_var_name}' or keyring ('{keyring_service}', '{keyring_username}')")
    
    return secret_value
