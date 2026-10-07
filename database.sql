-- ===================================================
-- College Event Management System - MySQL Database
-- Technologies: Python, MySQL, HTML, CSS
-- ===================================================

-- 1. Create Database
CREATE DATABASE IF NOT EXISTS college_event_db;
USE college_event_db;

-- 2. Users Table (Role-based access: admin / student)
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL
);

-- 3. Events Table
CREATE TABLE IF NOT EXISTS events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    event_description TEXT NOT NULL,
    event_date DATE NOT NULL,
    event_time TIME NOT NULL,
    venue VARCHAR(100) NOT NULL,
    organizer VARCHAR(100) NOT NULL,
    event_category VARCHAR(50) NOT NULL
);

-- 4. Event Participants Table (Student participation record)
CREATE TABLE IF NOT EXISTS event_participants (
    registration_id INT AUTO_INCREMENT PRIMARY KEY,
    event_id INT NOT NULL,
    user_id INT NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_event (event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ===================================================
-- Sample Data for Testing
-- ===================================================

-- Sample Users:
-- Admin: admin / admin123
-- Student: student / student123
INSERT INTO users (username, password, role) VALUES
('admin', 'admin123', 'admin'),
('student', 'student123', 'student')
ON DUPLICATE KEY UPDATE username=username;

-- Sample College Events
INSERT INTO events (event_name, event_description, event_date, event_time, venue, organizer, event_category) VALUES
('TechNova 2026', 'Inter-collegiate Technical Symposium featuring Web Development, Debugging, Paper Presentation, and Quiz.', '2026-10-18', '09:30:00', 'APJ Abdul Kalam Seminar Hall', 'Department of Computer Science', 'Technical'),
('Annual Athletics Meet', 'Annual college sports competitions including 100m sprint, relay, long jump, and shot put.', '2026-10-22', '08:00:00', 'College Main Sports Ground', 'Department of Physical Education', 'Sports'),
('Symphony Cultural Fest', 'Grand inter-department cultural celebration with classical dance, singing, photography, and mime.', '2026-10-28', '15:30:00', 'College Open Air Auditorium', 'College Fine Arts Club', 'Cultural'),
('National AI & Robotics Workshop', 'A one-day hands-on academic workshop on Artificial Intelligence trends and basics.', '2026-11-05', '10:00:00', 'Auditorium Block B', 'IQAC & CS Association', 'Academic');
