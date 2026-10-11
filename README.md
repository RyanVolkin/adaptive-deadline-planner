**Setup**

Use
  python -m venv .venv
to create the enviroment

Then use
  python -m pip install -r requirements.txt 
to install requirements

after pip installing, update the requirements.txt file with
  python -m pip freeze > requirements.txt



**Testing**

To manually run the tests in the test folder use
  python -m pytest

Tests will automatically run after you create a PR
