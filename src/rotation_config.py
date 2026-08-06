from dataclasses import dataclass

@dataclass
class RotationConfig:
    enabled: bool = True
    poll_interval: float = 30.0    # seconds
    reload_timeout: float = 10.0   # seconds for provider reload
    jitter: float = 3.0            # ± seconds jitter to avoid stampede
    secret_name: str = "OPENAI_API_KEY"
