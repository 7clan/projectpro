"""Verified, deterministic statics engine. SI conventions: m, kN, kN/m, kN·m.
A simply supported beam with a vertical point load and a uniform distributed load.
This is educational, not a structural design tool.
"""
from dataclasses import dataclass
from math import isclose


@dataclass(frozen=True)
class Beam:
    length: float = 8.0
    load: float = 12.0
    position: float = 2.0
    udl: float = 0.0

    def __post_init__(self):
        if not (2 <= self.length <= 20):
            raise ValueError("La portée doit être entre 2 et 20 m")
        if not (0 < self.position < self.length):
            raise ValueError("Le chargement ponctuel doit être entre les appuis")
        if not (0 <= self.load <= 100 and 0 <= self.udl <= 30):
            raise ValueError("Les charges doivent être positives et dans les limites")
        if self.load == 0 and self.udl == 0:
            raise ValueError("Au moins une charge est requise")

    @property
    def total_load(self):
        return self.load + self.udl * self.length

    @property
    def ra(self):
        return (self.load * (self.length - self.position) / self.length) + self.udl * self.length / 2

    @property
    def rb(self):
        return (self.load * self.position / self.length) + self.udl * self.length / 2

    def shear(self, x):
        if not (0 <= x <= self.length):
            raise ValueError("x hors de la poutre")
        return self.ra - self.udl * x - (self.load if x >= self.position else 0)

    def moment(self, x):
        if not (0 <= x <= self.length):
            raise ValueError("x hors de la poutre")
        return self.ra * x - self.udl * x * x / 2 - self.load * max(0, x - self.position)

    def critical_x(self):
        points = {0.0, self.position, self.length}
        if self.udl > 0:
            x_left = self.ra / self.udl
            x_right = (self.ra - self.load) / self.udl
            if 0 < x_left < self.position:
                points.add(x_left)
            if self.position < x_right < self.length:
                points.add(x_right)
        return max(points, key=self.moment)

    def overview(self, samples=61):
        xs = [self.length * i / (samples - 1) for i in range(samples)]
        xc = self.critical_x()
        return {
            "length": self.length,
            "load": self.load,
            "position": self.position,
            "udl": self.udl,
            "ra": round(self.ra, 4),
            "rb": round(self.rb, 4),
            "total_load": round(self.total_load, 4),
            "max_moment": round(self.moment(xc), 4),
            "max_moment_x": round(xc, 4),
            "shear": [round(self.shear(x), 4) for x in xs],
            "moment": [round(self.moment(x), 4) for x in xs],
            "x": [round(x, 4) for x in xs],
        }

    def expected_prediction(self):
        if isclose(self.ra, self.rb, abs_tol=1e-7):
            return "equal"
        return "left" if self.ra > self.rb else "right"

    def check(self, ra, rb):
        tolerance = max(0.12, 0.025 * self.total_load)
        ok_ra = abs(ra - self.ra) <= tolerance
        ok_rb = abs(rb - self.rb) <= tolerance
        mistake = None
        if not (ok_ra and ok_rb):
            if abs(ra - self.rb) <= tolerance and abs(rb - self.ra) <= tolerance:
                mistake = "moment_arms_reversed"
            elif abs((ra + rb) - self.load) <= tolerance and self.udl > 0:
                mistake = "forgot_distributed_load"
            elif abs((ra + rb) - self.total_load) > tolerance:
                mistake = "force_balance"
            elif abs(ra - rb) <= tolerance and abs(self.ra - self.rb) > tolerance:
                mistake = "symmetry_assumption"
            else:
                mistake = "moment_equilibrium"
        return {"correct": ok_ra and ok_rb, "ra_correct": ok_ra, "rb_correct": ok_rb,
                "misconception": mistake, "tolerance": round(tolerance, 3)}

    def validate_equilibrium(self):
        return (isclose(self.ra + self.rb, self.total_load, abs_tol=1e-9) and
                isclose(self.rb * self.length, self.load * self.position + self.udl * self.length ** 2 / 2, abs_tol=1e-9) and
                isclose(self.moment(0), 0, abs_tol=1e-9) and
                isclose(self.moment(self.length), 0, abs_tol=1e-9))


CONCEPTS = [
    {"id": "force_balance", "fr": "Équilibre des forces", "en": "Force equilibrium", "importance": 5},
    {"id": "moment_equilibrium", "fr": "Équilibre des moments", "en": "Moment equilibrium", "importance": 5},
    {"id": "support_reactions", "fr": "Réactions d'appui", "en": "Support reactions", "importance": 5},
    {"id": "load_transfer", "fr": "Transfert des acquis", "en": "Knowledge transfer", "importance": 4},
]

MISTAKES_FR = {
    "moment_arms_reversed": "Tu as probablement inversé les bras de levier. La charge proche d’un appui augmente sa réaction.",
    "forgot_distributed_load": "La charge répartie a été oubliée : sa résultante vaut q × L et agit au centre.",
    "force_balance": "Reprends ΣFy = 0 : RA + RB doit être égal à P + q × L.",
    "symmetry_assumption": "Les réactions ne sont égales que si la charge totale est symétrique.",
    "moment_equilibrium": "Vérifie ΣMA = 0 : RB × L = P × a + (q × L) × (L/2).",
}
MISTAKES_EN = {
    "moment_arms_reversed": "You may have reversed the moment arms. A load closer to a support increases that support's reaction.",
    "forgot_distributed_load": "You omitted the distributed load: its resultant is q × L, acting at midspan.",
    "force_balance": "Check ΣFy = 0: RA + RB must equal P + q × L.",
    "symmetry_assumption": "The reactions are equal only when the total loading is symmetric.",
    "moment_equilibrium": "Check ΣMA = 0: RB × L = P × a + (q × L) × (L/2).",
}


def explanation_check(text, lang="fr"):
    """Transparent keyword-based formative checklist, *not* AI grading."""
    value = text.casefold()
    parts = {
        "equilibrium": any(w in value for w in ("equilibr", "équilibr", "sum", "somme", "balance", "Σ", "force")),
        "moment": any(w in value for w in ("moment", "torque", "bras de levier")),
        "distance": any(w in value for w in ("distance", "position", "lever", "distance", "longueur", "length", "distance", "appui", "support")),
    }
    missing = [k for k, v in parts.items() if not v]
    msg_fr = {
        "equilibrium": "Mentionne explicitement l'équilibre des forces (ΣFy = 0).",
        "moment": "Explique le principe des moments autour d'un appui (ΣM = 0).",
        "distance": "Relie les bras de levier à la position de la charge.",
    }
    msg_en = {
        "equilibrium": "Explicitly state vertical force equilibrium (ΣFy = 0).",
        "moment": "Explain moment equilibrium about a support (ΣM = 0).",
        "distance": "Connect lever arms with the position of the load.",
    }
    return {"checklist": parts, "missing": missing, "quality": "complete" if not missing and len(text.strip()) > 35 else "revise",
            "feedback": "Bonne structure. Essaie maintenant un nouveau chargement pour vérifier ton transfert." if not missing and len(text.strip()) > 35 and lang == "fr" else
            "Good structure. Try a new load to check your understanding." if not missing and len(text.strip()) > 35 else
            " ".join((msg_fr if lang == "fr" else msg_en)[k] for k in missing) or
            ("Développe davantage ton raisonnement." if lang == "fr" else "Explain your reasoning in more detail.")}
