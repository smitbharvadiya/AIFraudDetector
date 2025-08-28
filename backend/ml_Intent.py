from open_intent_classifier.model import OpenAiIntentClassifier

labels = ["fraudulent", "safe", "phishing", "promotional", "legitimate"]

text = "Congratulations! You’ve won a free iPhone. Please share your credit card details to claim it."

model_name = "gpt-4o-mini"
classifier = OpenAiIntentClassifier(model_name)
result = classifier.predict(text=text, labels=labels)

print(result)
