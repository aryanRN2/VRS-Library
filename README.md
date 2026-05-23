# 📚 VRS Digital Library Management System

A premium, production-grade **Library Management and Seat Allotment Portal** designed for high-density modern study spaces. The system features a real-time interactive **Seat Matrix**, intelligent **Shift-Wise Conflict Management**, automated utility integrations like **WhatsApp Receipt Notifications**, and dynamic **ReportLab PDF receipts**.

The platform is **fully deployed on Vercel** and actively manages membership registration, real-time seat allocations, and financial records.

---

## 🎨 Visual Preview

Here is a visual overview of the VRS Digital Library interface. These screenshot files are stored inside the `for readme/` directory.

### 🏠 Home Page Interface
A sleek, modern glassmorphic landing page designed to welcome users, showcase membership options, and redirect them to their respective dashboards.
![VRS Library Home Page](for%20readme/HOME%20PAGE.png)

### 🪟 The Seat Matrix (Real-Time Booking & Transaction Management)
The core dashboard showing the 65-seat grid, color-coded by occupancy, shift, and request status, with instant reservation triggers.
![Seat Matrix Dashboard](for%20readme/SEAT%20MATRIX%20REAL%20TIME%20BOOKING%20WITH%20TRANSACTION%20MANAGMENT.png)

### 👥 Integrated Member Directory & Administration Panel
A comprehensive admin view showing active members, pending registrations, custom notes, profile photo processing, and messaging options.
![Admin Member Directory](for%20readme/ALL%20MEMBER%20QUERY%20INTRGRATED.png)

---

## 🚀 Key Features Explained In-Depth

### 1. 🪑 Interactive Real-Time Seat Matrix
The application operates on a **65-seat capacity system**. The seat matrix dashboard dynamically shows seat availability based on the selected shift.

*   **Shift Filtering:** Users and admins can filter the seat layout by **Morning**, **Evening**, or **Full Day** shifts.
*   **Visual State Coding:**
    *   🟢 **Vacant (Available):** Seat is unassigned and open for requests.
    *   🟡 **Requested (Pending):** The current user has requested this seat and is awaiting admin approval.
    *   🔴 **Occupied (Booked):** The seat is approved and occupied by another student for that shift.
    *   🔵 **Your Seat (My-Seat):** Denotes the seat currently allotted to the logged-in member.
*   **Dynamic Data Synchronization:** The client performs REST API calls `/api/seats?shift=<name>` to fetch clean JSON structures representing the state of each seat. Expiry checks run server-side on every seat-load request to automatically free seats whose tenancy has lapsed.

---

### 2. 🛡️ Preventing Multiple Bookings & Double Booking
To guarantee data integrity and eliminate conflicts in a high-demand library environment, the system implements a strict multi-tier booking prevention model:

#### A. Single Active Tenancy Constraint
A student is restricted to **exactly one** seat request or active booking across the entire system.
```python
# Rule: One user can only have ONE active request or booking across ALL shifts
existing = Booking.query.filter_by(user_id=current_user.id).first()
if existing:
    return jsonify({
        'success': False, 
        'message': 'You already have a seat request or booking. Please cancel it before making a new one.'
    }), 400
```

#### B. Conflicting Shift Protection
Before submitting a request, the engine checks for active approved bookings on the requested seat ID within overlapping shifts:
```python
if Booking.query.filter(
    Booking.seat_id == seat_id, 
    Booking.shift.in_(conflicting_shifts), 
    Booking.status == 'approved'
).first():
    return jsonify({'success': False, 'message': 'Seat already booked for a conflicting shift.'}), 400
```

#### C. Database Transactions and Concurrency Control
All reservation operations are executed inside SQLAlchemy-managed database transactions. When an admin approves a booking:
1. The target booking state transitions to `approved`.
2. All other **pending** requests for the same seat on conflicting shifts are automatically evicted from the database to prevent accidental double-allotment.
3. If any step fails (e.g., database connection loss or server failure), a traceback is caught, `db.session.rollback()` is executed, and database state reverts cleanly.

---

### 3. ⏰ Shift-Wise Allotment & Overlap Logic
Seats are offered in three shift options: **Morning**, **Evening**, and **Full Day**. Since the "Full Day" shift spans the duration of both individual shifts, the system implements overlapping conflict matrices:

| Requested Shift | Overlapping / Conflicting Shifts | Description |
| :--- | :--- | :--- |
| **Morning** | `['morning', 'full']` | Cannot share seat with another morning user or a full-day user. |
| **Evening** | `['evening', 'full']` | Cannot share seat with another evening user or a full-day user. |
| **Full Day** | `['morning', 'evening', 'full']` | Cannot share seat with any other occupant. |

#### Conflicting Shift Resolver Code:
```python
if shift == 'morning':
    conflicting_shifts = ['morning', 'full']
elif shift == 'evening':
    conflicting_shifts = ['evening', 'full']
else: # full
    conflicting_shifts = ['morning', 'evening', 'full']
```
When a seat booking is approved, all other pending requests in the system matching `seat_id` and overlapping with the new tenant's shift are purged immediately:
```python
others = Booking.query.filter(
    Booking.seat_id == booking.seat_id, 
    Booking.shift.in_(conflicting_shifts), 
    Booking.status == 'pending', 
    Booking.id != booking.id
).all()
for o in others: 
    db.session.delete(o)
db.session.commit()
```

---

### 4. 💬 Automated WhatsApp Messaging (Facebook Graph API)
To provide real-time updates to students, the application integrates with the official **WhatsApp Cloud API**.

#### A. Automated Credential & Receipt Delivery
When an admin approves a student's membership and seat booking, a formatted receipt is compiled and dispatched directly to their WhatsApp number.
*   **Target Payload Details:** It sends their allocated Seat Number, Shift selection, Validity timeline, Amount paid, and direct login credentials (username and temporary password) so they can immediately sign in.
*   **Interactive Link:** Includes the direct portal link: `https://vrs-library.vercel.app/login`.

#### B. Phone Number Normalization
Prior to API transmission, phone numbers undergo regex formatting:
```python
# Strip non-digits and automatically prepend India country code (91) if 10-digit number is provided
phone = "".join(filter(str.isdigit, booking.user.phone))
if len(phone) == 10: 
    phone = "91" + phone
```

#### C. API Integration:
Requests are dispatched to the Facebook Graph API endpoint:
`https://graph.facebook.com/v17.0/{phone_id}/messages`
Using headers containing a secure Bearer Token (`WHATSAPP_TOKEN`) and Payload containing the recipient target and message body JSON.

---

### 5. 🚪 Admin Eviction, Freezing & The Waiting Room
When a member's tenancy is terminated, or they fail to renew, admins can transition their profile state from `active` to `frozen` or manually evict them.

*   **Freezing Auto-Eviction:** Transitioning a member to a `frozen` status automatically drops any active seat reservation they hold, returning the seat to the public pool:
    ```python
    if new_status == 'frozen' and user.status == 'active':
        Booking.query.filter_by(user_id=user.id).delete()
    ```
*   **The Waiting Room:** If an admin evicts a member from a seat (but keeps their profile active), the member is automatically sent to the **Waiting Room** queue (`WaitingRoom` database model). This acts as a priority list, allowing the admin to easily see who is currently seatless and waiting for an open spot.

---

### 6. 📊 Financial Auditing, Excel & PDF Generation
*   **Financial Reports Dashboard:** Admins can view current month revenues, previous month metrics, and a historical 6-month visual revenue line chart directly on the dashboard.
*   **Universal Member Directory Export:** Full member rosters can be exported as `.xlsx` spreadsheets using `pandas` and `openpyxl`, filtered either globally or by a specific billing month (`/api/admin/export_finance`).
*   **PDF Receipts:** Members can download clean, professional receipts directly from their dashboard. These PDFs are dynamically compiled using **ReportLab** layout templates, featuring structured transaction outlines, and a stylized letterhead layout.

---

## 🛠️ Technology Stack

*   **Backend:** Python 3.x, Flask (Web framework)
*   **Database ORM:** Flask-SQLAlchemy (PostgreSQL in Production, SQLite in Development)
*   **Frontend:** Vanilla HTML5, CSS3 (Modern Glassmorphic styling, HSL colors, responsive grid structures), JavaScript (ES6+ fetch APIs)
*   **Security & Guardrails:** Flask-WTF (CSRF Protection), Flask-Limiter (Rate limiting against brute-force and request spam), PBKDF2 Password Hashing
*   **Document Generation & Export:** ReportLab (Dynamic PDF Receipts), Pandas & Openpyxl (Excel Financial Logs)
*   **Messaging:** Facebook Graph API (WhatsApp Cloud Messenger integration)
*   **Hosting:** Vercel (Serverless Server)

---

## ⚙️ Environment Variables Config (.env)

Ensure you set up the following environment variables in your deployment settings:

```ini
# Flask Configuration
SECRET_KEY=your_strong_random_secret_key_here

# Database Configuration
# Uses PostgreSQL in production (e.g., Supabase / Neon)
DATABASE_URL=postgresql://user:password@host:port/dbname

# WhatsApp Cloud API Configuration
WHATSAPP_TOKEN=your_permanent_access_token_here
WHATSAPP_PHONE_ID=your_phone_number_id_here

# Default Admin Credentials (Synced on startup)
ADMIN_USER=admin
ADMIN_PASS=your_strong_admin_password_here
```

---

## 🌍 Vercel Serverless Deployment

This project uses the `@vercel/python` builder defined in `vercel.json`:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ]
}
```

> [!IMPORTANT]
> Since Vercel is a serverless environment, local SQLite databases stored in `/tmp` will **not persist** between server spin-downs. In production, always configure `DATABASE_URL` pointing to a remote PostgreSQL database instance.
