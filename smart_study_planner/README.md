# StudyBuddy: Smart AI Study Planner

A beginner-friendly Flask + SQLite starter app with:
- Manual study-plan builder (plan name, exam date, study hours, subject, chapters, time estimate, priority)
- Persistent tasks with due date, estimated time, priority, and completion status
- Subject list
- Simple rescheduling for pending tasks
- Responsive web dashboard

## 1. Requirements
- Python 3.10 or newer
- Internet connection only if you want AI API replies or Google Fonts

## 2. Run on Windows
Open Command Prompt or VS Code terminal in this project folder:

```bash
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser.

If `py` doesn't work, try `python` instead.

## 3. Enable real AI replies (optional)
The app works without an API key, but chat responses are rule-based demo responses.
To enable OpenAI responses, set an API key in your terminal before running the app.
Never paste your API key into `app.py`, HTML, or a public repository.

Windows Command Prompt (for this terminal session only):
```bat
set OPENAI_API_KEY=your_api_key_here
python app.py
```

PowerShell:
```powershell
$env:OPENAI_API_KEY="your_api_key_here"
python app.py
```

Optional model override:
```bat
set OPENAI_MODEL=gpt-4.1-mini
```

API usage may incur charges according to your account and model pricing. If the API call fails, the chat falls back to demo replies.

## 4. What's intentionally simple in version 1
- This is a local, single-user prototype. There is no login or multi-user isolation.
- Rescheduling distributes pending tasks across the next seven days; it is a simple baseline, not a fully optimized timetable.
- Subjects are currently a list. Add chapter-level syllabus mapping in the next development phase.
- The manual plan builder creates one saved task per chapter. The schedule is a simple baseline and should be reviewed by the student.

## 5. Next development steps
1. Add chapters and syllabus imports.
2. Have AI return structured task suggestions, then show a confirmation screen before saving them.
3. Build a smarter schedule based on available study hours and deadlines.
4. Add authentication and per-user database access before deploying for multiple students.
5. Add tests, CSRF protection, rate limits, and production configuration before public deployment.
