from __future__ import annotations

import numpy as np


def accuracy_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Return standard sample accuracy.

    In this project, this is the same quantity used for weighted accuracy
    in the speech-emotion CV summary, because every sample contributes one
    count to the numerator and denominator.
    """
    if len(y_true) == 0:
        return 0.0
    return float((y_true == y_pred).mean())


def macro_f1_score(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> float:
    if len(y_true) == 0:
        return 0.0
    f1s = []
    for cls in range(num_classes):
        tp = float(np.sum((y_true == cls) & (y_pred == cls)))
        fp = float(np.sum((y_true != cls) & (y_pred == cls)))
        fn = float(np.sum((y_true == cls) & (y_pred != cls)))
        precision = tp / (tp + fp) if tp + fp > 0 else 0.0
        recall = tp / (tp + fn) if tp + fn > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall > 0 else 0.0
        f1s.append(f1)
    return float(np.mean(f1s))


def weighted_f1_score(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> float:
    """Return class-support-weighted F1."""
    if len(y_true) == 0:
        return 0.0
    total = len(y_true)
    score = 0.0
    for cls in range(num_classes):
        support = float(np.sum(y_true == cls))
        if support == 0:
            continue
        tp = float(np.sum((y_true == cls) & (y_pred == cls)))
        fp = float(np.sum((y_true != cls) & (y_pred == cls)))
        fn = float(np.sum((y_true == cls) & (y_pred != cls)))
        precision = tp / (tp + fp) if tp + fp > 0 else 0.0
        recall = tp / (tp + fn) if tp + fn > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall > 0 else 0.0
        score += (support / total) * f1
    return float(score)


def weighted_accuracy_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Return sample-weighted accuracy.

    For the current codebase, this aliases standard accuracy. The name is kept
    because the CREMA-D CV workflow reports the metric using the base-paper
    terminology of weighted accuracy (W-Acc).
    """
    if len(y_true) == 0:
        return 0.0
    return accuracy_score(y_true, y_pred)


def unweighted_accuracy_score(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> float:
    """Return unweighted accuracy (balanced accuracy over observed classes)."""
    if len(y_true) == 0:
        return 0.0
    scores = []
    for cls in range(num_classes):
        mask = y_true == cls
        support = float(mask.sum())
        if support == 0:
            continue
        cls_acc = float((y_pred[mask] == cls).mean()) if support > 0 else 0.0
        scores.append(cls_acc)
    return float(np.mean(scores)) if scores else 0.0
