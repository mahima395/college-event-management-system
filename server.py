import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import cookies
import uuid
import html

# Import MySQL database connection helper
from db_config import get_db_connection

# Server configuration
HOST = 'localhost'
PORT = 8000

# Base directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# In-memory session store: maps session_id -> {'user_id': ..., 'username': ..., 'role': ...}
SESSIONS = {}


def read_template(filename):
    """Helper to read HTML template content from templates directory."""
    path = os.path.join(TEMPLATES_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def get_category_badge(category):
    """Returns a styled HTML badge based on event category."""
    cat = (category or '').strip().lower()
    cat_class = 'badge-other'
    if cat == 'technical':
        cat_class = 'badge-technical'
    elif cat == 'cultural':
        cat_class = 'badge-cultural'
    elif cat == 'sports':
        cat_class = 'badge-sports'
    elif cat == 'academic':
        cat_class = 'badge-academic'
    return f'<span class="badge {cat_class}">{html.escape(category)}</span>'


class EventAppHandler(BaseHTTPRequestHandler):

    # -------------------------------------------------------------
    # Session & Cookie Helpers
    # -------------------------------------------------------------
    def get_current_user(self):
        """Retrieves currently logged-in user from request cookie session."""
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            return None
        
        cookie = cookies.SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            return None

        if 'session_id' in cookie:
            session_token = cookie['session_id'].value
            return SESSIONS.get(session_token)
        return None

    def create_session(self, user_data):
        """Creates a new session and returns cookie header value."""
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = user_data
        return f"session_id={session_id}; Path=/; HttpOnly"

    def destroy_session(self):
        """Removes session from store."""
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            cookie = cookies.SimpleCookie()
            try:
                cookie.load(cookie_header)
                if 'session_id' in cookie:
                    session_token = cookie['session_id'].value
                    SESSIONS.pop(session_token, None)
            except Exception:
                pass

    # -------------------------------------------------------------
    # Response Helpers
    # -------------------------------------------------------------
    def send_html(self, content, status=200, extra_headers=None):
        """Sends an HTML response."""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def redirect(self, location, set_cookie_header=None):
        """Sends a 303 See Other redirect."""
        self.send_response(303)
        self.send_header('Location', location)
        if set_cookie_header:
            self.send_header('Set-Cookie', set_cookie_header)
        self.end_headers()

    def parse_post_data(self):
        """Parses URL-encoded POST body into a dictionary."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        raw_dict = urllib.parse.parse_qs(body)
        # Flatten dictionary values
        return {k: v[0].strip() for k, v in raw_dict.items() if v}

    # -------------------------------------------------------------
    # HTTP GET Request Handler
    # -------------------------------------------------------------
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Serve static CSS file
        if path == '/static/style.css':
            css_path = os.path.join(STATIC_DIR, 'style.css')
            if os.path.exists(css_path):
                self.send_response(200)
                self.send_header('Content-Type', 'text/css')
                self.end_headers()
                with open(css_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
            return

        current_user = self.get_current_user()

        # Route: Root /
        if path == '/':
            if not current_user:
                self.redirect('/login')
            elif current_user['role'] == 'admin':
                self.redirect('/admin/dashboard')
            else:
                self.redirect('/student/dashboard')
            return

        # Route: Login
        if path == '/login':
            if current_user:
                if current_user['role'] == 'admin':
                    self.redirect('/admin/dashboard')
                else:
                    self.redirect('/student/dashboard')
                return

            error_msg = ''
            if 'error' in query_params:
                err_code = query_params['error'][0]
                if err_code == 'invalid':
                    error_msg = '<div class="alert alert-error">Invalid username or password! Please check credentials.</div>'
                elif err_code == 'dberror':
                    error_msg = '<div class="alert alert-error">Cannot connect to MySQL database. Please verify MySQL service is running.</div>'

            html_template = read_template('login.html')
            page = html_template.replace('{{MESSAGE}}', error_msg)
            self.send_html(page)
            return

        # Route: Logout
        if path == '/logout':
            self.destroy_session()
            self.redirect('/login', set_cookie_header="session_id=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
            return

        # Protected Routes Check
        if not current_user:
            self.redirect('/login')
            return

        # Route: Admin Dashboard
        if path == '/admin/dashboard':
            # Role security check
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            msg_html = ''
            if 'msg' in query_params:
                m = query_params['msg'][0]
                if m == 'added':
                    msg_html = '<div class="alert alert-success">Event was added successfully!</div>'
                elif m == 'updated':
                    msg_html = '<div class="alert alert-success">Event was updated successfully!</div>'
                elif m == 'deleted':
                    msg_html = '<div class="alert alert-success">Event was deleted successfully!</div>'

            # Fetch events with registered participant counts from MySQL
            conn = get_db_connection()
            if not conn:
                self.send_html("<h2>Database Connection Error</h2><p>Could not connect to MySQL.</p>")
                return

            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT e.*, COUNT(p.registration_id) AS participant_count
                FROM events e
                LEFT JOIN event_participants p ON e.event_id = p.event_id
                GROUP BY e.event_id
                ORDER BY e.event_date ASC
            """)
            events = cursor.fetchall()
            cursor.close()
            conn.close()

            # Build table rows in HTML
            rows_html = ""
            if not events:
                rows_html = '<tr><td colspan="8" style="text-align:center; color:#6b7280; padding:20px;">No events found. Click "+ Add New Event" to create one.</td></tr>'
            else:
                for ev in events:
                    badge = get_category_badge(ev['event_category'])
                    rows_html += f"""
                    <tr>
                        <td><strong>#{ev['event_id']}</strong></td>
                        <td><strong>{html.escape(ev['event_name'])}</strong></td>
                        <td>{badge}</td>
                        <td>{ev['event_date']}</td>
                        <td>{str(ev['event_time'])[:5]}</td>
                        <td>{html.escape(ev['venue'])}</td>
                        <td>
                            <a href="/admin/participants?event_id={ev['event_id']}" class="btn btn-secondary" style="font-size:12px; padding:4px 8px;">
                                👥 {ev['participant_count']} Members
                            </a>
                        </td>
                        <td>
                            <div class="actions-cell">
                                <a href="/event-details?id={ev['event_id']}" class="btn btn-secondary" style="font-size:12px; padding:4px 8px;">View</a>
                                <a href="/admin/edit-event?id={ev['event_id']}" class="btn btn-warning" style="font-size:12px; padding:4px 8px;">Edit</a>
                                <form method="POST" action="/admin/delete-event" class="inline-form">
                                    <input type="hidden" name="event_id" value="{ev['event_id']}">
                                    <button type="submit" class="btn btn-danger" style="font-size:12px; padding:4px 8px;" onclick="return confirm('Are you sure you want to delete this event?');">Delete</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    """

            html_template = read_template('admin_dashboard.html')
            page = html_template.replace('{{USERNAME}}', html.escape(current_user['username']))
            page = page.replace('{{MESSAGE}}', msg_html)
            page = page.replace('{{EVENT_ROWS}}', rows_html)
            self.send_html(page)
            return

        # Route: Admin Add Event Page
        if path == '/admin/add-event':
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            html_template = read_template('add_event.html')
            page = html_template.replace('{{USERNAME}}', html.escape(current_user['username']))
            page = page.replace('{{MESSAGE}}', '')
            self.send_html(page)
            return

        # Route: Admin Edit Event Page
        if path == '/admin/edit-event':
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            event_id = query_params.get('id', [None])[0]
            if not event_id:
                self.redirect('/admin/dashboard')
                return

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM events WHERE event_id = %s", (event_id,))
            ev = cursor.fetchone()
            cursor.close()
            conn.close()

            if not ev:
                self.redirect('/admin/dashboard')
                return

            # Build category dropdown with selected state
            categories = ['Cultural', 'Sports', 'Technical', 'Academic', 'Other']
            cat_options = ""
            for cat in categories:
                selected = 'selected' if ev['event_category'] == cat else ''
                cat_options += f'<option value="{cat}" {selected}>{cat}</option>\n'

            html_template = read_template('edit_event.html')
            page = html_template.replace('{{USERNAME}}', html.escape(current_user['username']))
            page = page.replace('{{EVENT_ID}}', str(ev['event_id']))
            page = page.replace('{{EVENT_NAME}}', html.escape(ev['event_name']))
            page = page.replace('{{CATEGORY_OPTIONS}}', cat_options)
            page = page.replace('{{ORGANIZER}}', html.escape(ev['organizer']))
            page = page.replace('{{EVENT_DATE}}', str(ev['event_date']))
            page = page.replace('{{EVENT_TIME}}', str(ev['event_time'])[:5])
            page = page.replace('{{VENUE}}', html.escape(ev['venue']))
            page = page.replace('{{EVENT_DESCRIPTION}}', html.escape(ev['event_description']))
            page = page.replace('{{MESSAGE}}', '')
            self.send_html(page)
            return

        # Route: Admin View Participants Page
        if path == '/admin/participants':
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            event_id = query_params.get('event_id', [None])[0]
            if not event_id:
                self.redirect('/admin/dashboard')
                return

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # Fetch event details
            cursor.execute("SELECT event_name, event_date, venue FROM events WHERE event_id = %s", (event_id,))
            ev = cursor.fetchone()

            if not ev:
                cursor.close()
                conn.close()
                self.redirect('/admin/dashboard')
                return

            # Fetch participants
            cursor.execute("""
                SELECT u.username, p.registered_at
                FROM event_participants p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.event_id = %s
                ORDER BY p.registered_at DESC
            """, (event_id,))
            participants = cursor.fetchall()
            cursor.close()
            conn.close()

            # Build participant table rows
            rows_html = ""
            if not participants:
                rows_html = '<tr><td colspan="3" style="text-align:center; color:#6b7280; padding:20px;">No students have registered for this event yet.</td></tr>'
            else:
                for idx, pt in enumerate(participants, 1):
                    reg_time = str(pt['registered_at'])[:19]
                    rows_html += f"""
                    <tr>
                        <td>{idx}</td>
                        <td><strong>{html.escape(pt['username'])}</strong></td>
                        <td>{reg_time}</td>
                    </tr>
                    """

            html_template = read_template('view_participants.html')
            page = html_template.replace('{{USERNAME}}', html.escape(current_user['username']))
            page = page.replace('{{EVENT_NAME}}', html.escape(ev['event_name']))
            page = page.replace('{{EVENT_DATE}}', str(ev['event_date']))
            page = page.replace('{{VENUE}}', html.escape(ev['venue']))
            page = page.replace('{{TOTAL_PARTICIPANTS}}', str(len(participants)))
            page = page.replace('{{PARTICIPANT_ROWS}}', rows_html)
            self.send_html(page)
            return

        # Route: Student Dashboard
        if path == '/student/dashboard':
            msg_html = ''
            if 'msg' in query_params:
                m = query_params['msg'][0]
                if m == 'participated':
                    msg_html = '<div class="alert alert-success">Successfully registered for the event!</div>'
                elif m == 'already':
                    msg_html = '<div class="alert alert-error">You are already registered for this event.</div>'

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # Fetch events and check if this student has participated
            cursor.execute("""
                SELECT e.*, 
                       (SELECT COUNT(*) FROM event_participants WHERE event_id = e.event_id AND user_id = %s) AS is_registered
                FROM events e
                ORDER BY e.event_date ASC
            """, (current_user['user_id'],))
            events = cursor.fetchall()
            cursor.close()
            conn.close()

            # Build student table rows
            rows_html = ""
            if not events:
                rows_html = '<tr><td colspan="9" style="text-align:center; color:#6b7280; padding:20px;">No events available at this moment.</td></tr>'
            else:
                for ev in events:
                    badge = get_category_badge(ev['event_category'])
                    
                    # Participation button or registered status
                    if ev['is_registered'] > 0:
                        part_action = '<span class="badge badge-registered">✓ Registered</span>'
                    else:
                        part_action = f"""
                        <form method="POST" action="/student/participate" class="inline-form">
                            <input type="hidden" name="event_id" value="{ev['event_id']}">
                            <button type="submit" class="btn btn-success" style="font-size:12px; padding:4px 10px;">Participate</button>
                        </form>
                        """

                    rows_html += f"""
                    <tr>
                        <td>#{ev['event_id']}</td>
                        <td><strong>{html.escape(ev['event_name'])}</strong></td>
                        <td>{badge}</td>
                        <td>{ev['event_date']}</td>
                        <td>{str(ev['event_time'])[:5]}</td>
                        <td>{html.escape(ev['venue'])}</td>
                        <td>{html.escape(ev['organizer'])}</td>
                        <td>{part_action}</td>
                        <td>
                            <a href="/event-details?id={ev['event_id']}" class="btn btn-secondary" style="font-size:12px; padding:4px 8px;">View</a>
                        </td>
                    </tr>
                    """

            html_template = read_template('student_dashboard.html')
            page = html_template.replace('{{USERNAME}}', html.escape(current_user['username']))
            page = page.replace('{{MESSAGE}}', msg_html)
            page = page.replace('{{EVENT_ROWS}}', rows_html)
            self.send_html(page)
            return

        # Route: Event Details Page (Accessible to both Admin and Student)
        if path == '/event-details':
            event_id = query_params.get('id', [None])[0]
            if not event_id:
                back = '/admin/dashboard' if current_user['role'] == 'admin' else '/student/dashboard'
                self.redirect(back)
                return

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM events WHERE event_id = %s", (event_id,))
            ev = cursor.fetchone()

            is_registered = 0
            if current_user['role'] == 'student':
                cursor.execute("SELECT COUNT(*) AS cnt FROM event_participants WHERE event_id = %s AND user_id = %s",
                               (event_id, current_user['user_id']))
                res = cursor.fetchone()
                is_registered = res['cnt'] if res else 0

            cursor.close()
            conn.close()

            if not ev:
                back = '/admin/dashboard' if current_user['role'] == 'admin' else '/student/dashboard'
                self.redirect(back)
                return

            # Action buttons based on role
            back_url = '/admin/dashboard' if current_user['role'] == 'admin' else '/student/dashboard'
            role_badge = 'ADMIN' if current_user['role'] == 'admin' else 'STUDENT'
            action_buttons = ""

            if current_user['role'] == 'admin':
                action_buttons = f"""
                <a href="/admin/edit-event?id={ev['event_id']}" class="btn btn-warning">Edit Event</a>
                <a href="/admin/participants?event_id={ev['event_id']}" class="btn btn-primary">View Participants</a>
                """
            else:
                if is_registered > 0:
                    action_buttons = '<span class="badge badge-registered" style="padding:8px 14px; font-size:14px;">✓ You are Registered for this Event</span>'
                else:
                    action_buttons = f"""
                    <form method="POST" action="/student/participate" class="inline-form">
                        <input type="hidden" name="event_id" value="{ev['event_id']}">
                        <button type="submit" class="btn btn-success">Click to Participate</button>
                    </form>
                    """

            html_template = read_template('event_details.html')
            page = html_template.replace('{{USERNAME}}', html.escape(current_user['username']))
            page = page.replace('{{ROLE_BADGE}}', role_badge)
            page = page.replace('{{BACK_URL}}', back_url)
            page = page.replace('{{EVENT_ID}}', str(ev['event_id']))
            page = page.replace('{{EVENT_NAME}}', html.escape(ev['event_name']))
            page = page.replace('{{CATEGORY_BADGE}}', get_category_badge(ev['event_category']))
            page = page.replace('{{EVENT_DATE}}', str(ev['event_date']))
            page = page.replace('{{EVENT_TIME}}', str(ev['event_time'])[:5])
            page = page.replace('{{VENUE}}', html.escape(ev['venue']))
            page = page.replace('{{ORGANIZER}}', html.escape(ev['organizer']))
            page = page.replace('{{EVENT_DESCRIPTION}}', html.escape(ev['event_description']))
            page = page.replace('{{ACTION_BUTTONS}}', action_buttons)
            page = page.replace('{{MESSAGE}}', '')
            self.send_html(page)
            return

        # 404 Not Found
        self.send_html("<h2>404 Not Found</h2><p>The requested page does not exist. <a href='/'>Go Home</a></p>", status=404)

    # -------------------------------------------------------------
    # HTTP POST Request Handler
    # -------------------------------------------------------------
    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        post_data = self.parse_post_data()

        # POST: /login
        if path == '/login':
            username = post_data.get('username', '').strip()
            password = post_data.get('password', '').strip()

            conn = get_db_connection()
            if not conn:
                self.redirect('/login?error=dberror')
                return

            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                cookie_header = self.create_session({
                    'user_id': user['user_id'],
                    'username': user['username'],
                    'role': user['role']
                })
                if user['role'] == 'admin':
                    self.redirect('/admin/dashboard', set_cookie_header=cookie_header)
                else:
                    self.redirect('/student/dashboard', set_cookie_header=cookie_header)
            else:
                self.redirect('/login?error=invalid')
            return

        # Protected POST Requests Check
        current_user = self.get_current_user()
        if not current_user:
            self.redirect('/login')
            return

        # POST: /admin/add-event
        if path == '/admin/add-event':
            # Role validation
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            event_name = post_data.get('event_name', '')
            event_category = post_data.get('event_category', 'Other')
            event_date = post_data.get('event_date', '')
            event_time = post_data.get('event_time', '')
            venue = post_data.get('venue', '')
            organizer = post_data.get('organizer', '')
            event_description = post_data.get('event_description', '')

            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO events (event_name, event_description, event_date, event_time, venue, organizer, event_category)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (event_name, event_description, event_date, event_time, venue, organizer, event_category))
                conn.commit()
                cursor.close()
                conn.close()

            self.redirect('/admin/dashboard?msg=added')
            return

        # POST: /admin/edit-event
        if path == '/admin/edit-event':
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            event_id = post_data.get('event_id')
            event_name = post_data.get('event_name', '')
            event_category = post_data.get('event_category', 'Other')
            event_date = post_data.get('event_date', '')
            event_time = post_data.get('event_time', '')
            venue = post_data.get('venue', '')
            organizer = post_data.get('organizer', '')
            event_description = post_data.get('event_description', '')

            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE events 
                    SET event_name = %s, event_description = %s, event_date = %s, event_time = %s, venue = %s, organizer = %s, event_category = %s
                    WHERE event_id = %s
                """, (event_name, event_description, event_date, event_time, venue, organizer, event_category, event_id))
                conn.commit()
                cursor.close()
                conn.close()

            self.redirect('/admin/dashboard?msg=updated')
            return

        # POST: /admin/delete-event
        if path == '/admin/delete-event':
            if current_user['role'] != 'admin':
                self.redirect('/student/dashboard')
                return

            event_id = post_data.get('event_id')
            if event_id:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM events WHERE event_id = %s", (event_id,))
                    conn.commit()
                    cursor.close()
                    conn.close()

            self.redirect('/admin/dashboard?msg=deleted')
            return

        # POST: /student/participate
        if path == '/student/participate':
            if current_user['role'] != 'student':
                self.redirect('/admin/dashboard')
                return

            event_id = post_data.get('event_id')
            if event_id:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute("""
                            INSERT INTO event_participants (event_id, user_id)
                            VALUES (%s, %s)
                        """, (event_id, current_user['user_id']))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        self.redirect('/student/dashboard?msg=participated')
                        return
                    except Exception:
                        cursor.close()
                        conn.close()
                        self.redirect('/student/dashboard?msg=already')
                        return

            self.redirect('/student/dashboard')
            return

        # Unrecognized POST route
        self.send_html("<h2>404 Not Found</h2>", status=404)


def run_server():
    """Starts the Python HTTP Server."""
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, EventAppHandler)
    print("=" * 60)
    print(f"College Event Management System is running!")
    print(f"URL: http://{HOST}:{PORT}")
    print("Press Ctrl + C to stop the server.")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()
        print("Server stopped.")


if __name__ == '__main__':
    run_server()
