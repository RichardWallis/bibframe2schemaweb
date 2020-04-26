import os

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY','Schema.org rules!')
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4MB max-limit.
    
    
    
TestMode = False
