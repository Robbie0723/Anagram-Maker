import logging
import random
import boto3
from datetime import datetime
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model.ui import SimpleCard
from ask_sdk_model import Response
from itertools   import combinations,product
from collections import Counter,defaultdict

client = boto3.client('dynamodb')
sns_client = boto3.client('sns')
sb = SkillBuilder()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


with open("words","r") as wordFile:
	words = wordFile.read().split("\n")

anagrams = defaultdict(set)
for word in words:
	anagrams["".join(sorted(word))].add(word)
counters = { w:Counter(w) for w in anagrams }
minLen   = 2 # minimum word length


def iMultigram(word,prefix=""):
	sWord = "".join(sorted(word))
	seen = set()
	for anagram in anagrams.get(sWord,[]):
		full = prefix+anagram
		if full in seen or seen.add(full): continue
		yield full        
	wordCounts = counters.get(sWord,Counter(word))
	for size in reversed(range(minLen,len(word)-minLen+1)): # longest first           
		for combo in combinations(sWord,size):
			left  = "".join(sorted(combo))
			if left in seen or seen.add(left): continue
			for left in iMultigram(left,prefix):
				right = "".join((wordCounts-Counter(combo)).elements())
				for full in iMultigram(right,left+" "):
					if full in seen or seen.add(full): continue
					yield full


	  
def send_email(userid):
	message = 'Anagram Maker 2.0 is being used by the following user: {}' .format(userid)
	response = sns_client.publish(
		TopicArn='arn:aws:sns:us-east-1:???????????:alexa_skills_email',
		Message= message,
		Subject='Anagram Maker 2.0 has been activated',
		MessageStructure='string'
	)
	return response



def add_item(session_attr):
	time = str(datetime.now())	
	response = client.put_item(
		Item={
			'TimeStamp': {
				'S': time,
			},
			'UserID': {
				'S': str(session_attr['user_id']),
			},
			'Word': {
				'S': str(session_attr['user_word'])
			},
		},
		ReturnConsumedCapacity='TOTAL',
		TableName='Anagram',
)



class LaunchRequestHandler(AbstractRequestHandler):
	"""Handler for Skill Launch."""
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return is_request_type("LaunchRequest")(handler_input)

	def handle(self, handler_input):
		#send email notifying me that game is activated.
		user_id = handler_input.request_envelope.session.user.user_id
		send_email(user_id)

		speech_text = "Welcome to Anagram Maker!  Please provide a word to search for.  For example, an anagram of Listen is Silent.  What word are you searching for? "
		reprompt = "If you provide me with a word, I can give you examples of anagrams for that word."
		handler_input.response_builder.speak(speech_text).ask(reprompt).set_card(
			SimpleCard("Anagram Maker", speech_text)).set_should_end_session(
			False)
		return handler_input.response_builder.response



class MakeAnagram(AbstractRequestHandler):
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return is_intent_name("makeanagram")(handler_input)

	def handle(self, handler_input):
		# type: (HandlerInput) -> Response
		session_attr = handler_input.attributes_manager.session_attributes
		session_attr['user_id'] = handler_input.request_envelope.session.user.user_id
		slots = handler_input.request_envelope.request.intent.slots
		session_attr['user_word'] = slots['word'].value
		results = iMultigram(session_attr['user_word'])
		alexa_list = []

		try:
			for i in range(5):
				r = next(results)
				if r != session_attr['user_word']:
					alexa_list.append(r)
		except StopIteration:
			pass

		audio = '<audio src="soundbank://soundlibrary/ui/gameshow/amzn_ui_sfx_gameshow_tally_positive_01"/>'

		if len(alexa_list) == 0:
			speech_text = f"""Unfortunately, we couldn't find an anagram for "{session_attr['user_word']}".  Is there  another word you would like to try?"""
		elif len(alexa_list) ==1:
			speech_text = f"""An anagram of "{session_attr['user_word']}" is "{alexa_list[0]}".  Would you like to hear another word?"""
		elif len(alexa_list) > 1:
			speech_text  = f"""Some anagrams of "{session_attr['user_word']}" are "{alexa_list[0]}" and "{alexa_list[1]}".  Would you like to hear another word?"""

		speak_output = audio + speech_text

		reprompt = "I did not hear your response.  Would you like me to search for another word?"
		handler_input.response_builder.speak(speak_output).ask(reprompt).set_card(
			SimpleCard("Anagram Maker 2.0", speech_text)).set_should_end_session(
			False)

		#adding to DynamoDB
		add_item(session_attr)
		return handler_input.response_builder.response




class HelpIntentHandler(AbstractRequestHandler):
	"""Handler for Help Intent."""
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return is_intent_name("AMAZON.HelpIntent")(handler_input)

	def handle(self, handler_input):
		# type: (HandlerInput) -> Response
		speech_text = "This is a fun skill that will create anagrams of words provided by the user.  Simply tell us a word when prompted and we will give you an example of an anagram of that word.  What word would you like to hear  an anagram of?"
		reprompt = "Would you like me to search for an anagram of a word?"
		handler_input.response_builder.speak(speech_text).ask(
			reprompt).set_card(SimpleCard(
				"Anagram Mkaker 2.0", speech_text)).set_should_end_session(False)
		return handler_input.response_builder.response




class YesIntentHandler(AbstractRequestHandler):
	"""Handler for Session End."""
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return is_intent_name("AMAZON.YesIntent")(handler_input)

	def handle(self, handler_input):
		# type: (HandlerInput) -> Response

		speech_text = "Great!  What word should I search for next?"
		reprompt = "If you provide me with a word, I can give you examples of anagrams for that word."
		handler_input.response_builder.speak(speech_text).ask(reprompt).set_card(
			SimpleCard("Anagram Maker 2.0", speech_text)).set_should_end_session(
			False)
		return handler_input.response_builder.response


class CancelOrStopIntentHandler(AbstractRequestHandler):
	"""Single handler for Cancel and Stop Intent."""
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return (is_intent_name("AMAZON.CancelIntent")(handler_input) or
				is_intent_name("AMAZON.StopIntent")(handler_input))
				

	def handle(self, handler_input):
		# type: (HandlerInput) -> Response
		speech_text = "Thank you for visiting us.  We hope you had fun!"
		 
		handler_input.response_builder.speak(speech_text).set_card(
			SimpleCard("Ending Anagram Maker 2.0", speech_text))
		return handler_input.response_builder.response


class FallbackIntentHandler(AbstractRequestHandler):
	"""AMAZON.FallbackIntent is only available in en-US locale.
	This handler will not be triggered except in that locale,
	so it is safe to deploy on any locale.
	"""
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return is_intent_name("AMAZON.FallbackIntent")(handler_input)

	def handle(self, handler_input):
		# type: (HandlerInput) -> Response
		speech_text = "I'm sorry, I couldn't hear that.  Please repeat the word you would like me to search for. "
		reprompt = "I'm sorry, I couldn't hear that.  Please repeat. "
		handler_input.response_builder.speak(speech_text).ask(reprompt)
		return handler_input.response_builder.response


class SessionEndedRequestHandler(AbstractRequestHandler):
	"""Handler for Session End."""
	def can_handle(self, handler_input):
		# type: (HandlerInput) -> bool
		return is_request_type("SessionEndedRequest")(handler_input)

	def handle(self, handler_input):
		# type: (HandlerInput) -> Response
		return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
	"""Catch all exception handler, log exception and
	respond with custom message.
	"""
	def can_handle(self, handler_input, exception):
		# type: (HandlerInput, Exception) -> bool
		return True

	def handle(self, handler_input, exception):
		# type: (HandlerInput, Exception) -> Response
		logger.error(exception, exc_info=True)

		speech = "I'm sorry, but we have appeared to have run into a problem.  Please try again next time."
		handler_input.response_builder.speak(speech).ask(speech)

		return handler_input.response_builder.response


sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(YesIntentHandler())
sb.add_request_handler(MakeAnagram())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())


sb.add_exception_handler(CatchAllExceptionHandler())

handler = sb.lambda_handler()