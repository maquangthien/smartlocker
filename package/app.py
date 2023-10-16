import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import string
from flask import flash
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'


db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="PassW0rk#123Wen",
    database="smart_locker1"
)
cursor = db.cursor()

def generate_user_id():
    cursor = db.cursor()
    cursor.execute("SELECT MAX(user_id) FROM users")
    result = cursor.fetchone()
    cursor.close()

    if result[0] is not None:
        current_id = int(result[0][1:])
        next_id = current_id + 1
        user_id = f"U{next_id:03d}"
    else:
        user_id = "U001"

    return user_id

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    phone_exists = False
    email_exists = False

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form['role']

        if password != confirm_password:
            return "Mật khẩu và xác nhận mật khẩu không khớp"

        cursor = db.cursor()
        cursor.execute("SELECT role_id FROM roles WHERE role_name = %s", (role,))
        role_id = cursor.fetchone()[0]

        cursor.execute("SELECT phone FROM users WHERE phone = %s", (phone,))
        existing_user_by_phone = cursor.fetchone()
        phone_exists = existing_user_by_phone is not None

        cursor.execute("SELECT mail FROM users WHERE mail = %s", (email,))
        existing_user_by_email = cursor.fetchone()
        email_exists = existing_user_by_email is not None

        if phone_exists:
            error_message = "Số điện thoại đã tồn tại."
        elif email_exists:
            error_message = "Email đã tồn tại. "
        else:
            user_id = generate_user_id()

            insert_query = "INSERT INTO users (user_id, name, mail, phone, role_id, password) VALUES (%s, %s, %s, %s, %s, %s)"
            values = (user_id, name, email, phone, role_id, password)
            cursor.execute(insert_query, values)

            db.commit()
            cursor.close()

            return redirect(url_for('login'))

        return render_template('register.html', error_message=error_message, phone_exists=phone_exists, email_exists=email_exists)

    return render_template('register.html')

@app.route('/update_profile', methods=['GET', 'POST'])
def update_profile():
    if 'user_id' in session:
        user_id = session['user_id']
        cursor = db.cursor()

        if request.method == 'POST':
            new_name = request.form['name']
            new_mail = request.form['mail']
            new_phone = request.form['phone']

            cursor.execute("UPDATE users SET name = %s, mail = %s, phone = %s WHERE user_id = %s",
                           (new_name, new_mail, new_phone, user_id))
            db.commit()

            cursor.execute("SELECT name, mail, phone FROM users WHERE user_id = %s", (user_id,))
            user_info = cursor.fetchone()
            user_name = user_info[0]
            user_mail = user_info[1]
            user_phone = user_info[2]

            cursor.close()

            flash('Cập nhật thông tin cá nhân thành công', 'success')
            return redirect(url_for('process_locker'))

        cursor.execute("SELECT name, mail, phone FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        user_name = user_info[0]
        user_mail = user_info[1]
        user_phone = user_info[2]

        cursor.close()
        return render_template('update_profile.html', user_name=user_name, user_mail=user_mail, user_phone=user_phone)

    return "Vui lòng đăng nhập để cập nhật thông tin cá nhân."

@app.route('/login', methods=['GET', 'POST'])
def login():
    valid_credentials = True
    error_message = None
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']

        cursor = db.cursor()
        cursor.execute("SELECT user_id, name, role_id FROM users WHERE phone = %s AND password = %s", (phone, password))
        user = cursor.fetchone()

        if user:
            session['user_id'] = user[0]
            user_name = user[1]
            role_id = user[2]

            cursor.close()

            if role_id == '3':
                return render_template('otp_delivery.html', user_name=user_name)
            elif role_id == '2':
                return render_template('process_locker.html', user_name=user_name)
            elif role_id == '1':
                return render_template('admin.html', user_name=user_name)
            else:
                valid_credentials = False

        else:
            valid_credentials = False
            error_message = "Sai số điện thoại hoặc mật khẩu. Vui lòng thử lại."

    return render_template('login.html', valid_credentials=valid_credentials, error_message=error_message)

@app.route('/user')
def user():
    if 'user_id' in session:
        return render_template('user.html')
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/history', methods=['GET'])
def history():
    if 'user_id' in session:
        user_id = session['user_id']
        cursor = db.cursor()
        cursor.execute("SELECT codeorders, user_sender, user_receiver, start_time, end_time FROM histories WHERE user_sender = %s OR user_receiver = %s", (user_id, user_id))
        histories = cursor.fetchall()
        cursor.close()

        for i, history in enumerate(histories):
            histories[i] = list(history)
            if history[-1] is None:
                histories[i][-1] = "Chưa hoàn thành"

        return render_template('history.html', histories=histories)
    else:
        return "Vui lòng đăng nhập để xem lịch sử sử dụng tủ."

@app.route('/process_locker', methods=['GET', 'POST'])
def process_locker():
    if request.method == 'POST':
        cursor = db.cursor()
        try:
            name = request.form['name']
            mail = request.form['mail']
            phone = request.form['phone']
            user_receiver_phone = request.form['phone1']
            start_time = request.form['start_time']

            # Kiểm tra xem số điện thoại của người gửi có tồn tại trong bảng "users" hay không
            cursor.execute("SELECT user_id FROM users WHERE phone = %s", (phone,))
            user = cursor.fetchone()

            if user:
                cursor.execute("SELECT locker_id FROM lockers WHERE status = 'off' LIMIT 1")
                available_locker = cursor.fetchone()

                if available_locker:
                    locker_id = available_locker[0]

                    cursor.execute("SELECT user_id FROM users WHERE phone = %s", (user_receiver_phone,))
                    user_receiver = cursor.fetchone()

                    if user_receiver:
                        user_sender = user[0]
                        start_time = datetime.now()

                        otp_sender = generate_otp()
                        otp_deliver = generate_otp()
                        otp_receiver = generate_otp()
                        expiration_time = datetime.now() + timedelta(hours=3)

                        codeorders = generate_random_code()

                        cursor.execute(
                            "INSERT INTO otps (otp_sender, otp_deliver, otp_receiver, expiration_time, codeorders) VALUES (%s, %s, %s, %s, %s)",
                            (otp_sender, otp_deliver, otp_receiver, expiration_time, codeorders))
                        db.commit()

                        cursor.execute(
                            "INSERT INTO histories (codeorders, user_sender, user_receiver, start_time) VALUES (%s, %s, %s, %s)",
                            (codeorders, user_sender, user_receiver[0], start_time))
                        db.commit()

                        session['otp_sender'] = otp_sender
                        session['otp_deliver'] = otp_deliver
                        session['otp_receiver'] = otp_receiver
                        session['codeorders'] = codeorders

                        cursor.close()

                        if send_otp_sender(mail, otp_sender):
                            return redirect(url_for('otp_sender'))
                    else:
                        return "Số điện thoại người nhận không tồn tại trong hệ thống."
                else:
                    return "Không có tủ trống để đặt."
            else:
                return "Số điện thoại người gửi không tồn tại trong hệ thống."

        except Exception as e:
            return str(e)
    return render_template('process_locker.html')



def generate_random_code():
    digits = ''.join(random.choices(string.digits, k=4))
    letters = ''.join(random.choices(string.ascii_letters, k=4))
    code = digits + letters
    return code

def generate_otp():
    return str(random.randint(1000, 9999))

def send_otp_sender(mail, otp_sender):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "2051010118huyen@ou.edu.vn"
    smtp_password = "nguyenthithuhuyen"

    msg = MIMEMultipart()
    msg['From'] = "2051010118huyen@ou.edu.vn"
    msg['To'] = mail
    msg['Subject'] = "Thông tin đặt tủ"

    body = f"Mã OTP là: {otp_sender}\nVui lòng không cung cấp mã này cho bất kì ai. Mã OTP có thời gian sử dụng là 3 tiếng."
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, mail, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Lỗi khi gửi email: {str(e)}")
        return False
@app.route('/otp_sender')
def otp_sender():
    if 'otp_sender' in session:
        otp_sender = session['otp_sender']
        return render_template('otp_sender.html', otp_sender=otp_sender)
    else:
        return redirect(url_for('process_locker'))

@app.route('/unlock_locker', methods=['POST'])
def unlock_locker():
    if request.method == 'POST':
        otp_sender = request.form['otp_sender']
        codeorders = session.get('codeorders')

        # Kiểm tra xác thực OTP
        if otp_sender == session.get('otp_sender'):
            cursor = db.cursor()

            # Tìm tủ trống (status='off')
            cursor.execute("SELECT locker_id FROM lockers WHERE status = 'off' ORDER BY RAND() LIMIT 1")
            available_locker = cursor.fetchone()

            if available_locker:
                locker_id = available_locker[0]

                # Cập nhật trạng thái tủ thành "on" (status='on')
                cursor.execute("UPDATE lockers SET status = 'on' WHERE locker_id = %s", (locker_id,))
                db.commit()

                otp_processing = generate_otp()
                code_orders = generate_random_code()

                # Truy vấn thông tin từ bảng histories dựa trên codeorders
                cursor.execute("SELECT user_sender, start_time FROM histories WHERE codeorders = %s", (codeorders,))
                history_info = cursor.fetchone()

                if history_info:
                    user_sender = history_info[0]
                    start_time = history_info[1]

                    cursor.execute(
                        "INSERT INTO otpprocessing (user_id, locker_id, otp, codeorders) VALUES (%s, %s, %s, %s)",
                        (user_sender, locker_id, otp_sender, codeorders)
                    )
                    db.commit()
                else:
                    return "Không tìm thấy thông tin từ bảng histories."

                db.commit()

                cursor.close()

                session.pop('otp_sender', None)

                return render_template('unlock_success.html', locker_number=locker_id)

    return redirect(url_for('process_locker'))

def send_otp_deliver(mail, otp_deliver):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "2051010118huyen@ou.edu.vn"
    smtp_password = "nguyenthithuhuyen"

    # Tạo email
    msg = MIMEMultipart()
    msg['From'] = "2051010118huyen@ou.edu.vn"
    msg['To'] = mail
    msg['Subject'] = "Mã OTP_deliver"

    body = f"Mã OTP là: {otp_deliver}\nVui lòng không cung cấp mã này cho bất kì ai. Mã OTP có thời gian sử dụng là 3 tiếng."
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, mail, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Lỗi khi gửi email: {str(e)}")
        return False

@app.route('/close_locker', methods=['POST'])
def close_locker():
    cursor = db.cursor()

    # Kiểm tra xem có tủ nào trống (status='off') không
    cursor.execute("SELECT locker_id FROM lockers WHERE status = 'off' LIMIT 1")
    available_locker = cursor.fetchone()

    if available_locker:
        locker_id = available_locker[0]
        codeorders = session.get('codeorders')
        cursor.execute("SELECT otp_deliver FROM otps WHERE codeorders = %s", (codeorders,))
        otp_deliver = cursor.fetchone()

        if otp_deliver:
            cursor.execute("SELECT user_id FROM users WHERE role_id = 3")
            shipper_user_id = cursor.fetchone()

            if shipper_user_id:
                # Lấy địa chỉ email của người giao hàng dựa trên user_id
                cursor.execute("SELECT mail FROM users WHERE user_id = %s", (shipper_user_id[0],))
                shipper_email = cursor.fetchone()

                if shipper_email:
                    otp_deliver = otp_deliver[0]  # Lấy giá trị của mã OTP_deliver

                    if send_otp_deliver(shipper_email[0], otp_deliver):
                        # Cập nhật user_deliver trong bảng histories
                        cursor.execute(
                            "UPDATE histories SET user_deliver = %s WHERE codeorders = %s",
                            (shipper_user_id[0], codeorders)
                        )

                        cursor.execute("SELECT otpprocessing_id FROM otpprocessing WHERE codeorders = %s",
                                       (codeorders,))
                        otpprocessing_record = cursor.fetchone()

                        if otpprocessing_record:
                            otpprocessing_id = otpprocessing_record[0]

                            cursor.execute(
                                "UPDATE otpprocessing SET user_id = %s, otp = %s WHERE otpprocessing_id = %s",
                                (shipper_user_id[0], otp_deliver, otpprocessing_id)
                            )

                        db.commit()

                        cursor.close()

                        return render_template('process_locker.html')
                    else:
                        return "Gửi mã OTP_deliver không thành công."
                else:
                    return "Không tìm thấy địa chỉ email của người giao hàng trong cơ sở dữ liệu."
            else:
                return "Không tìm thấy người giao hàng (shipper) có role_id = 3 trong cơ sở dữ liệu."
        else:
            return "Không tìm thấy mã OTP_deliver trong bảng otps."
    else:
        return "Không có tủ trống nào để đóng và kết thúc."



@app.route('/otp_delivery', methods=['GET'])
def otp_delivery():
    return render_template('otp_delivery.html')

@app.route('/validate_otp', methods=['POST'])
def validate_otp():
    if request.method == 'POST':
        entered_otp = request.form['otp']

        # Lấy mã OTP_deliver từ biến session
        otp_deliver = session.get('otp_deliver')

        if entered_otp == otp_deliver:
            session.pop('otp_deliver', None)

            return redirect(url_for('locker_opened'))
        else:
            # Mã OTP không đúng, hiển thị thông báo lỗi
            error_message = "Mã OTP không đúng. Vui lòng thử lại."
            return render_template('otp_delivery.html', error_message=error_message)

@app.route('/locker_opened', methods=['GET'])
def locker_opened():
    # Lấy locker_id từ bảng otpprocessing dựa trên codeorders
    cursor = db.cursor()
    cursor.execute("SELECT locker_id FROM otpprocessing WHERE codeorders = %s", (session['codeorders'],))
    locker_id_result = cursor.fetchone()
    cursor.close()

    locker_id = locker_id_result[0] if locker_id_result else None

    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM otpprocessing WHERE codeorders = %s", (session['codeorders'],))
    opened_lockers_result = cursor.fetchone()
    cursor.close()

    opened_lockers = opened_lockers_result[0] if opened_lockers_result else 0

    return render_template('locker_opened.html', locker_id=locker_id, opened_lockers=opened_lockers)

@app.route('/finish_delivery', methods=['POST'])
def finish_delivery():
    cursor = db.cursor()

    if request.method == 'POST':
        locker_id = request.form.get('locker_id')  # Lấy giá trị locker_id từ biểu mẫu

        if locker_id:
            cursor.execute("UPDATE lockers SET status = 'off' WHERE locker_id = %s", (locker_id,))
            db.commit()

            cursor.execute("SELECT locker_id FROM lockers WHERE status = 'off'")
            available_lockers = cursor.fetchall()

            if available_lockers:
                chosen_locker = random.choice(available_lockers)
                chosen_locker_id = chosen_locker[0]

                # Cập nhật chosen_locker_id vào bảng otpprocessing
                cursor.execute("UPDATE otpprocessing SET locker_id = %s WHERE locker_id = %s", (chosen_locker_id, locker_id))
                db.commit()

                cursor.close()

                # Lưu chosen_locker_id vào biến session để sử dụng sau này
                session['chosen_locker_id'] = chosen_locker_id

                return render_template('otp_second_input.html')

    return "Không tìm thấy giá trị locker_id trong dữ liệu POST."

@app.route('/open_new_locker', methods=['POST'])
def open_new_locker():
    cursor = db.cursor()

    if request.method == 'POST':
        otp_deliver = request.form.get('otp_deliver')  # Lấy giá trị mã OTP_deliver từ biểu mẫu

        if otp_deliver:
            # Kiểm tra xem mã OTP_deliver có chính xác không
            cursor.execute("SELECT locker_id FROM otpprocessing WHERE codeorders = %s AND otp = %s", (session['codeorders'], otp_deliver))
            locker_id = cursor.fetchone()

            if locker_id:
                # Cập nhật trạng thái của tủ mới thành "on"
                cursor.execute("UPDATE lockers SET status = 'on' WHERE locker_id = %s", (locker_id[0],))
                db.commit()

                # Xóa thông tin về mã OTP_deliver đã sử dụng
                # cursor.execute("DELETE FROM otpprocessing WHERE codeorders = %s", (session['codeorders'],))
                # db.commit()

                cursor.close()

                return render_template('deliver_locker_opened.html', locker_id=locker_id[0])

    return "Mã OTP không hợp lệ hoặc không tìm thấy trong dữ liệu POST."

def send_otp_receiver(mail, otp_receiver ):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "2051010118huyen@ou.edu.vn"
    smtp_password = "nguyenthithuhuyen"

    # Tạo email
    msg = MIMEMultipart()
    msg['From'] = "2051010118huyen@ou.edu.vn"
    msg['To'] = mail
    msg['Subject'] = "Mã OTP nhận hàng "

    body = f"Mã OTP là: {otp_receiver }\nVui lòng không cung cấp mã này cho bất kì ai. Mã OTP có thời gian sử dụng là 3 tiếng."
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Gửi email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, mail, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Lỗi khi gửi email: {str(e)}")
        return False

@app.route('/finishtwo_delivery', methods=['POST'])
def finishtwo_delivery():
    cursor = db.cursor()

    if request.method == 'POST':
        # Lấy mã otp_receiver từ bảng otps sử dụng codeorders từ biến session
        cursor.execute("SELECT otp_receiver FROM otps WHERE codeorders = %s", (session['codeorders'],))
        otp_receiver = cursor.fetchone()

        if otp_receiver:
            otp_receiver = otp_receiver[0]

            # Truy vấn user_id của người nhận hàng (user_receiver) trong bảng histories qua codeorders
            cursor.execute("SELECT user_receiver FROM histories WHERE codeorders = %s", (session['codeorders'],))
            user_receiver = cursor.fetchone()

            if user_receiver:
                user_receiver = user_receiver[0]  # Lấy giá trị user_receiver từ tuple

                # Truy vấn địa chỉ email của người nhận hàng từ bảng users
                cursor.execute("SELECT mail FROM users WHERE user_id = %s", (user_receiver,))
                email_receiver = cursor.fetchone()

                if email_receiver:
                    email_receiver = email_receiver[0]  # Lấy địa chỉ email từ tuple

                    # Gửi mã otp_receiver cho người nhận hàng (user_receiver) qua email
                    if send_otp_receiver(email_receiver, otp_receiver):
                        # Kiểm tra xem có bất kỳ bản ghi nào có cùng giá trị codeorders
                        cursor.execute("UPDATE otpprocessing SET user_id = %s, otp = %s WHERE codeorders = %s", (user_receiver, otp_receiver, session['codeorders']))
                        db.commit()

                        cursor.close()

                        return "Đã cập nhật thông tin User Receiver và OTP trong bảng otpprocessing."
                    else:
                        return "Không thể gửi email cho người nhận hàng. Vui lòng kiểm tra cài đặt email của hệ thống."
                else:
                    return "Không tìm thấy địa chỉ email của người nhận hàng trong hệ thống."
            else:
                return "Không tìm thấy thông tin người nhận hàng hoặc dữ liệu POST không hợp lệ."
    return "Không tìm thấy thông tin hoặc dữ liệu POST không hợp lệ."


@app.route('/receiver_verify_otp', methods=['GET', 'POST'])
def receiver_verify_otp():
    return render_template('otp_receiver.html')
@app.route('/receiver_otp', methods=['POST'])
def receiver_otp():
    if request.method == 'POST':
        entered_otp = request.form['otp']

        if 'user_id' in session:
            user_id = session['user_id']

            # Làm các thao tác kiểm tra mã OTP và user_id trong bảng otpprocessing ở đây
            cursor = db.cursor()
            cursor.execute("SELECT locker_id FROM otpprocessing WHERE otp = %s AND user_id = %s",
                           (entered_otp, user_id))
            locker_info = cursor.fetchone()
            cursor.close()

            if locker_info:
                locker_id = locker_info[0]  # Lấy giá trị locker_id từ tuple

                session['locker_id'] = locker_id

                session['entered_otp'] = entered_otp
                # Nếu mã OTP và user_id trùng khớp, hiển thị locker_id
                return render_template('otp_verification_result.html', locker_id=locker_id)

            else:
                # Nếu không trùng khớp, hiển thị thông báo lỗi
                return "Mã OTP hoặc user_id không hợp lệ. Vui lòng thử lại."

        else:
            # Xử lý trường hợp không có user_id trong biến session
            return "Vui lòng đăng nhập để xác minh OTP."

        # Hiển thị biểu mẫu nhập OTP (bạn có thể thay đổi HTML tùy ý)
    return render_template('otp_receiver.html')


@app.route('/complete_receiver', methods=['POST'])
def complete_receiver():
    if 'user_id' in session:
        user_id = session['user_id']
        entered_otp = session.get('entered_otp')
        print("entered_otp:", entered_otp)
        if entered_otp:
            cursor = db.cursor()

            locker_id = session.get('locker_id')

            if locker_id is not None:
                # Cập nhật trạng thái tủ locker_id trong bảng lockers về 'off'
                cursor.execute("UPDATE lockers SET status = 'off' WHERE locker_id = %s", (locker_id,))

                cursor.execute("SELECT codeorders FROM otpprocessing WHERE otp = %s", (entered_otp,))
                codeorders = cursor.fetchone()
                if codeorders:
                    codeorders = codeorders[0]
                    current_time = datetime.now()
                    end_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute("UPDATE histories SET end_time = %s WHERE codeorders = %s",
                                   (end_time, codeorders))
                    db.commit()

                    # Xóa các thông tin liên quan khỏi biến session
                    session.pop('entered_otp', None)
                    session.pop('locker_id', None)

                    cursor.close()

                    return "Bạn đã hoàn thành việc lấy hàng. Tủ đã được đóng."
                else:
                    return "Không thể tìm thấy mã đơn hàng (codeorders) dựa trên mã OTP."

            else:
                return "Không thể cập nhật trạng thái tủ vì locker_id không được đặt trong biến session."
        else:
            return "Vui lòng đăng nhập và xác thực OTP để hoàn thành việc lấy hàng."
    else:
        return "Vui lòng đăng nhập để xác thực OTP và hoàn thành việc lấy hàng."


@app.route('/manage_lockers')
def manage_lockers():
    cursor = db.cursor()
    cursor.execute("SELECT locker_id, location, status FROM lockers")
    lockers = cursor.fetchall()
    cursor.close()
    return render_template('manage_lockers.html', lockers=lockers)

@app.route('/add_locker', methods=['POST'])
def add_locker():
    if request.method == 'POST':
        # Xử lý thêm tủ vào cơ sở dữ liệu dựa trên dữ liệu biểu mẫu
        locker_id = request.form['locker_id']
        location = request.form['location']
        status = request.form['status']

        cursor = db.cursor()
        insert_query = "INSERT INTO lockers (locker_id, location, status) VALUES (%s, %s, %s)"
        values = (locker_id, location, status)
        cursor.execute(insert_query, values)
        db.commit()
        cursor.close()

    return redirect(url_for('manage_lockers'))

@app.route('/edit_locker', methods=['POST'])
def edit_locker():
    if request.method == 'POST':
        # Xử lý sửa tủ dựa trên dữ liệu biểu mẫu
        locker_id = request.form['locker_id']
        new_location = request.form['new_location']
        new_status = request.form['new_status']

        cursor = db.cursor()
        cursor.execute("UPDATE lockers SET location = %s, status = %s WHERE locker_id = %s",
                       (new_location, new_status, locker_id))
        db.commit()
        cursor.close()

    return redirect(url_for('manage_lockers'))

@app.route('/delete_locker', methods=['POST'])
def delete_locker():
    if request.method == 'POST':
        # Xử lý xóa tủ dựa trên mã tủ
        locker_id = request.form['locker_id']

        cursor = db.cursor()
        cursor.execute("DELETE FROM lockers WHERE locker_id = %s", (locker_id,))
        db.commit()
        cursor.close()

    return redirect(url_for('manage_lockers'))


@app.route('/manage_users', methods=['GET', 'POST'])
def manage_users():
    if request.method == 'POST':
        # Thêm tài khoản
        if request.form.get('action') == 'add':
            user_id = request.form['user_id']
            name = request.form['name']
            mail = request.form['mail']
            phone = request.form['phone']
            role_id = request.form['role_id']
            password = request.form['password']

            cursor.execute("INSERT INTO users (user_id, name, mail, phone, role_id, password) VALUES (%s, %s, %s, %s, %s, %s)",
                           (user_id, name, mail, phone, role_id, password))
            db.commit()

        # Sửa tài khoản
        elif request.form.get('action') == 'edit':
            user_id = request.form['user_id']
            new_name = request.form['new_name']
            new_mail = request.form['new_mail']
            new_phone = request.form['new_phone']
            new_role_id = request.form['new_role_id']
            new_password = request.form['new_password']

            cursor.execute("UPDATE users SET name = %s, mail = %s, phone = %s, role_id = %s, password = %s WHERE user_id = %s",
                           (new_name, new_mail, new_phone, new_role_id, new_password, user_id))
            db.commit()

        # Xóa tài khoản
        elif request.form.get('action') == 'delete':
            user_id = request.form['user_id']

            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            db.commit()

    # Lấy dữ liệu từ bảng users
    cursor.execute("SELECT user_id, name, mail, phone, role_id, password FROM users")
    users = cursor.fetchall()

    return render_template('manage_users.html', users=users)


@app.route('/view_logs')
def view_logs():
    cursor.execute("SELECT codeorders, user_sender, user_deliver, user_receiver, start_time, end_time FROM histories")

    logs = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('manage_history.html', logs=logs)

@app.route('/search_logs', methods=['POST'])
def search_logs():
    if request.method == 'POST':
        search_text = request.form['search_text'].lower()
        cursor.execute("SELECT codeorders, user_sender, user_deliver, user_receiver, start_time, end_time FROM histories "
                       "WHERE LOWER(codeorders) LIKE %s OR LOWER(user_sender) LIKE %s",
                       (f"%{search_text}%", f"%{search_text}%"))
        logs = cursor.fetchall()
        cursor.close()
        db.close()

        return render_template('manage_history.html', logs=logs)
if __name__ == '__main__':
    app.run()
