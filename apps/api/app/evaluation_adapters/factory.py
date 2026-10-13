from .adapter import EvaluationAdapter
from .vally import VallyAdapter
from .waza import WazaAdapter


def get_adapter(name: str) -> EvaluationAdapter:
    adapters: dict[str, type[EvaluationAdapter]] = {
        "vally": VallyAdapter,
        "waza": WazaAdapter,
    }
    try:
        return adapters[name.casefold()]()
    except KeyError:
        raise ValueError(f"Unsupported evaluation adapter: {name}") from None
