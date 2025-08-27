import re

# Each rule = (pattern, weight, label)
RULES = [
    (r"(send|transfer|deposit).*(money|funds|amount)", 0.6, "Money Transfer Request"),
    (r"(urgent|immediate|now).*(payment|transfer|action)", 0.5, "Urgency with Payment"),
    (r"(share|tell|give).*(otp|verification\s+code)|(otp|verification\s+code).*(share|tell|give)?", 0.9, "OTP/Verification Code Request"),
    (r"(your\s+account).*(blocked|suspended|closed)", 0.8, "Account Suspension Threat"),
    (r"(pay|payment).*(link|request|immediately)", 0.7, "Suspicious Payment Link"),
]

def detect_intent(text: str):
    matches = []
    total_score = 0.0
    max_possible = sum(weight for _, weight, _ in RULES)  # normalization factor

    for pattern, weight, label in RULES:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            matches.append({
                "label": label,
                "matched_text": match.group(0)
            })
            total_score += weight

    score = round(total_score / max_possible, 2) if max_possible > 0 else 0.0

    # Risk levels
    if score >= 0.7:
        risk = "HIGH"
    elif score >= 0.3:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "text": text,
        "rule_matches": matches,
        "rule_score": score,
        "risk_level": risk
    }

if __name__ == "__main__":
    test_sentences = [
        "Please transfer money immediately.",
        "Share your OTP with me.",
        "Your account will be suspended.",
        "Can you send the document?",
        "Let’s meet tomorrow."
    ]

    for s in test_sentences:
        print(detect_intent(s))
