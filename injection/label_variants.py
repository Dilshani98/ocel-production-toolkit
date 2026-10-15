import random
import string


def _split_camel(label):
    out, cur = [], ""
    for ch in label:
        if ch.isupper() and cur:
            out.append(cur); cur = ch
        else:
            cur += ch
    return out + [cur]


def _distort(label, mode, rng):
    i = rng.randrange(1, len(label) - 1)          # never touch first/last letter
    if mode == "deletion":
        return label[:i] + label[i + 1:]
    if mode == "transposition":
        return label[:i] + label[i + 1] + label[i] + label[i + 2:]
    if mode == "substitution":
        new = rng.choice([c for c in string.ascii_lowercase if c != label[i].lower()])
        return label[:i] + new + label[i + 1:]
    if mode == "case_spacing":
        return rng.choice([label.lower(), label.upper(), " ".join(_split_camel(label))])
    raise ValueError(f"Unknown mode: {mode}")


def distort_labels(labels, severity, seed, mode, only_label=None):
    """Returns (new_labels, truth) where truth maps row position -> original label."""
    rng = random.Random(seed)
    new = labels.copy()
    eligible = [i for i, v in enumerate(labels) if only_label is None or v == only_label]
    chosen = rng.sample(eligible, int(len(eligible) * severity))
    truth = {}
    for i in chosen:
        original = labels.iloc[i]
        bad = _distort(original, mode, rng)
        if bad != original:
            new.iloc[i] = bad
            truth[i] = original
    return new, truth