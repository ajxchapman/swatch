import logging

# Setup logging
logging.DEV = logging.DEBUG + 5
logging.addLevelName(logging.DEV, 'DEV') 