"""Entry point for CEMS - AGC Campus Event Management System.

Run with:      python app.py
"""

import os

from cems import create_app
from cems.extensions import db

app = create_app()


@app.shell_context_processor
def shell_context():
    from cems import models

    return {
        "db": db,
        "User": models.User,
        "Event": models.Event,
        "Registration": models.Registration,
        "Attendance": models.Attendance,
        "Feedback": models.Feedback,
        "Notice": models.Notice,
        "Certificate": models.Certificate,
    }


@app.cli.command("create-demo-account")
def create_demo_account():
    """Create an account for a role: python app.py create-demo-account -r student."""
    import click
    from cems.models import ROLE_STUDENT, User
    from cems.seed import DEMO_PASSWORD

    role = click.prompt("Role (STUDENT/FACULTY/ORGANIZER)", default=ROLE_STUDENT).upper()
    email = click.prompt("Email")
    password = click.prompt("Password", default=DEMO_PASSWORD, hide_input=False)
    name = click.prompt("Full name")

    if User.query.filter_by(email=email.lower()).first():
        click.echo("That email already exists.")
        return
    user = User(name=name, email=email.lower(), role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f"Created {role} account {email}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG", "1") != "0")