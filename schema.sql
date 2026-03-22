create table customer
(customer_id int primary key auto_increment,
cust_name varchar(50) not null,
email varchar(50) not null unique,
phone varchar(15) not null unique,
address varchar(255) not null,
region enum('North', 'South', 'East', 'West') not null,
login_id int unique)auto_increment=100;

create table service
(service_id int primary key auto_increment,
service_name varchar(50) not null,
category enum('pickup', 'onsite') not null,
price decimal(10, 2) not null,
service_type enum('regular','premium'))auto_increment=1000;

create table worker
(worker_id int primary key auto_increment,
worker_name varchar(50) not null,
phone varchar(15) not null unique,
email varchar(50) not null unique,
address varchar(255) not null,
skills varchar(255) not null,
login_id int unique)auto_increment=10000;

create table booking
(booking_id int primary key auto_increment,
booking_date date not null,
booking_time time not null,
booking_status enum('pending','completed', 'cancelled') not null,
customer_id int,
service_id int,
worker_id int,
foreign key (customer_id) references customer(customer_id),
foreign key (service_id) references service(service_id),
foreign key (worker_id) references worker(worker_id))auto_increment=100000;

create table payment
(payment_id int primary key auto_increment,
amount decimal(10, 2) not null,
payment_status enum('pending', 'completed','cancelled') not null,
payment_method enum('cash','online') not null,
booking_id int,
foreign key (booking_id) references booking(booking_id))auto_increment=200000;

create table login
(login_id int primary key auto_increment,
username varchar(50) not null unique,
password varchar(255) not null,
role enum('customer', 'worker','admin') not null)auto_increment=300000;

create table provides
(service_id int,
worker_id int,
primary key(service_id, worker_id),
foreign key(service_id) references service(service_id),
foreign key(worker_id) references worker(worker_id));

alter table customer add foreign key (login_id) references login(login_id);
alter table worker add foreign key (login_id) references login(login_id);

create table worker_pending
(pending_id int primary key auto_increment,
worker_name varchar(50) not null,
phone varchar(15) not null unique,
email varchar(50) not null unique,
address varchar(255) not null,
skills varchar(255) not null,
username varchar(50) not null unique,
password varchar(255) not null,
registration_date timestamp default current_timestamp
)auto_increment=200000;

create table feedback
(feedback_id int primary key auto_increment,
booking_id int not null,
rating int not null check (rating >= 1 and rating <= 5),
comments text,
created_at timestamp default current_timestamp,
foreign key (booking_id) references booking(booking_id))auto_increment=400000;

create table pending_registrations
(email varchar(50) primary key,
 user_data json not null,
 otp varchar(10) not null,
 role enum('customer', 'worker') not null,
 expires_at timestamp not null
);

create table otp_store
(otp_id int primary key auto_increment,
 email varchar(50) not null,
 otp varchar(10) not null,
 purpose enum('login', 'password_reset') not null,
 expires_at timestamp not null,
 unique key (email, purpose)
);
