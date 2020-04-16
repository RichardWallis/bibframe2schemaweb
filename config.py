import os

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY','Schema.org rules!')
    
    
TestMode = False
def testModeSet(mode=False):
        global TestMode
        print("setting %s" % mode)
        TestMode = mode
        