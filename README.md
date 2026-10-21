**Running**
This application builds of main and runs at

https://adaptive-deadline-planner.onrender.com

**Setup**

Use
  python -m venv .venv
to create the enviroment

Then use
  python -m pip install -r requirements.txt 
to install requirements

Create a local `.env` file with your Supabase project credentials:

  SUPABASE_URL=https://your-project.supabase.co
  SUPABASE_KEY=your-anon-key
  SECRET_KEY=change-this-for-local-development

The application uses Supabase Auth for local, test, and production authentication. It will not start without `SUPABASE_URL` and `SUPABASE_KEY` unless a client is explicitly injected by a test.

after pip installing, update the requirements.txt file with
  python -m pip freeze > requirements.txt



**Testing**

To manually run the tests in the test folder use
  python -m pytest

Tests will automatically run after you create a PR
