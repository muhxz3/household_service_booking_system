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
service_type enum('regular','emergency','premium'))auto_increment=1000;

create table worker
(worker_id int primary key auto_increment,
worker_name varchar(50) not null,
phone varchar(15) not null unique,
email varchar(50) not null unique,
address varchar(255) not null,
skills varchar(255) not null,
is_24_7 boolean default false,
rating decimal(3, 2) default 0.00,
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
is_24_7 boolean default false,
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

create table subscription_plan
(plan_id int primary key auto_increment,
 plan_name varchar(50) not null,
 price decimal(10, 2) not null,
 duration_months int not null default 3,
 description text
)auto_increment=500;

create table subscription_benefit
(benefit_id int primary key auto_increment,
 plan_id int not null,
 service_id int not null,
 quantity int not null,
 is_unlimited boolean default false,
 foreign key (plan_id) references subscription_plan(plan_id),
 foreign key (service_id) references service(service_id)
)auto_increment=550;

create table customer_subscription
(subscription_id int primary key auto_increment,
 customer_id int not null,
 plan_id int not null,
 start_date date not null,
 end_date date not null,
 status enum('active', 'expired', 'cancelled', 'pending') default 'pending',
 foreign key (customer_id) references customer(customer_id),
 foreign key (plan_id) references subscription_plan(plan_id) 
)auto_increment=600;

create table service_credits
(credit_id int primary key auto_increment,
 subscription_id int not null,
 service_id int not null,
 remaining_quantity int not null,
 is_unlimited boolean default false,
 foreign key (subscription_id) references customer_subscription(subscription_id) on delete cascade,
 foreign key (service_id) references service(service_id)
)auto_increment=700;

alter table booking add column subscription_id int;
alter table booking add foreign key (subscription_id) references customer_subscription(subscription_id) on delete cascade;

alter table payment add column subscription_id int;
alter table payment add foreign key (subscription_id) references customer_subscription(subscription_id) on delete cascade;

create table otp_store
(otp_id int primary key auto_increment,
 email varchar(50) not null,
 otp varchar(10) not null,
 purpose enum('login', 'password_reset', 'email_change') not null,
 expires_at timestamp not null,
 unique key (email, purpose)
);
