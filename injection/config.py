from dataclasses import dataclass

@dataclass
class InjectionConfig:
    pattern: str          # Inject pattern name
    severity: float       # fraction of eligible records affected, e.g. 0.05, 0.15, 0.30
    seed: int = 42         # follow FLAWD's stochastic design (every run should be reproducible)