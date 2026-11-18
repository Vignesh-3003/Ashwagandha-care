"""The five Ashwagandha problems — the only answers the model may give.

Keep these keys in step with `KB` in static/js/app.js: the page looks its cards
up by key, so an unknown key would leave the result panel empty.
"""
from __future__ import annotations

CONDITIONS: dict[str, dict] = {
    "healthy": {
        "key": "healthy",
        "name": "Healthy Ashwagandha leaf",
        "latin": "No problem signature",
        "severity": "None",
        "short": (
            "Even green tissue, no spots, no curling, no chewed edges. Keep watering lightly, "
            "keep the plot drained, scout weekly."
        ),
    },
    "damping": {
        "key": "damping",
        "name": "Seedling Blight / Damping-off",
        "latin": "Pythium / Rhizoctonia spp.",
        "severity": "High",
        "short": (
            "Seedlings rot at soil level and fall over. Remove affected seedlings, reduce watering, "
            "use a recommended fungicide; prevent it with Trichoderma seed treatment and well-drained soil."
        ),
    },
    "spot": {
        "key": "spot",
        "name": "Alternaria Leaf Spot",
        "latin": "Alternaria alternata",
        "severity": "Medium",
        "short": (
            "Brown spots with rings that merge and dry. Remove affected leaves and spray a "
            "recommended fungicide such as mancozeb; prevent it with spacing, crop rotation and clean fields."
        ),
    },
    "rootrot": {
        "key": "rootrot",
        "name": "Root Rot / Wilt",
        "latin": "Fusarium / Sclerotium rolfsii",
        "severity": "High",
        "short": (
            "Plants yellow and wilt, roots turn brown and rotten. There is no cure once severe — "
            "remove affected plants; prevent it with drainage, no over-watering, rotation and Trichoderma."
        ),
    },
    "hadda": {
        "key": "hadda",
        "name": "Hadda Beetle",
        "latin": "Epilachna spp.",
        "severity": "Medium",
        "short": (
            "Leaves eaten into a net-like pattern by yellow grubs and spotted adults. Hand-pick "
            "beetles and larvae, spray neem seed extract, and check the field weekly."
        ),
    },
    "mites": {
        "key": "mites",
        "name": "Aphids & Red Spider Mites",
        "latin": "Aphis spp. / Tetranychus urticae",
        "severity": "Medium",
        "short": (
            "Curled, sticky or speckled leaves from sap-sucking insects. Spray neem oil or soap "
            "water; avoid dusty, over-fertilized crops."
        ),
    },
}

KEYS: list[str] = list(CONDITIONS)


def is_condition(value: object) -> bool:
    """True only for a key the page can actually render."""
    return isinstance(value, str) and value in CONDITIONS


def context_for(key: str | None) -> str:
    """Compact context handed to the chat model so answers stay grounded."""
    condition = CONDITIONS.get(key or "")
    lines = []
    if condition:
        lines += [
            f"Diagnosed problem: {condition['name']} ({condition['latin']}), "
            f"severity {condition['severity']}.",
            f"Standard guidance: {condition['short']}",
            "",
        ]
    lines.append("All problems this tool knows:")
    lines += [f"- {c['name']}: {c['short']}" for c in CONDITIONS.values()]
    return "\n".join(lines)
