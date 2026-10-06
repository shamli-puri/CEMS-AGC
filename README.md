CEMS — Campus Event Management System

CEMS (Campus Event Management System) is a web-based platform designed to simplify and digitize the management of college campus events.

The system provides separate interfaces for Students, Faculty, and Organizers, allowing users to discover events, register for events, manage participation, generate digital tickets, track attendance, provide feedback, and manage certificates.

🚀 Features

- Student, Faculty, and Organizer authentication
- Role-based dashboards
- Event creation and management
- Event discovery and registration
- Digital QR tickets
- QR-based attendance management
- Registration and participant management
- Digital certificate management
- Event feedback system
- Campus notices and announcements
- User profile management
- Event statistics and analytics
- Responsive and user-friendly interface

🛠️ Technologies Used

- Frontend: HTML5, CSS3, JavaScript
- Backend: Python, Flask
- Database: SQLite
- ORM: SQLAlchemy
- QR Code: Python QR Code libraries
- Testing: Pytest

👥 User Roles

Student

Students can:

- Browse upcoming events
- Register for events
- View registrations
- Access digital QR tickets
- Track attendance
- View certificates
- Submit feedback
- View campus notices

Faculty

Faculty members can:

- Manage events
- View participants and registrations
- Manage attendance
- View feedback
- Publish and manage notices

Organizer

Organizers can:

- Create and manage events
- Manage registrations
- View participants
- Scan/manage QR-based attendance
- Manage certificates
- View event statistics
- Manage feedback and notices

📂 Project Structure

CEMS-AGC/
├── app.py
├── config.py
├── requirements.txt
├── cems/
│   ├── routes/
│   ├── services/
│   └── utils/
├── templates/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
└── tests/

⚙️ Installation & Setup

1. Clone the repository

git clone https://github.com/shamli-puri/CEMS-AGC.git
cd CEMS-AGC

2. Create a virtual environment

python -m venv .venv

3. Activate the virtual environment

Windows:

.venv\Scripts\activate

4. Install dependencies

pip install -r requirements.txt

5. Configure environment variables

Create a ".env" file using ".env.example" as a reference and add the required configuration values.

6. Run the application

python app.py

Then open the local URL shown by Flask in your browser.

🧪 Testing

The project includes automated tests using Pytest.

Run:

pytest

🎯 Project Objective

The main objective of CEMS is to provide a centralized digital platform for managing campus events efficiently while reducing manual registration, attendance, communication, and certificate-management processes.

🔮 Future Enhancements

- Mobile application
- Advanced event recommendation system
- Email and notification automation
- Advanced analytics dashboard
- Cloud deployment
- Improved QR-based attendance security

📌 Project Status

Academic Project — Campus Event Management System

Developed as a B.Tech Computer Science and Engineering project.
