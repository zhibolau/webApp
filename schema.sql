drop database if EXISTS awesome;-- 每个sql语句要有冒号!!!!!!!!

CREATE database awesome;

use awesome;

grant select, insert, update, delete on awesome.* to 'root'@'localhost' identified by 'password';

create table users( -- 是(  不是{}
 `id` VARCHAR(50) not NULL,
 `email` VARCHAR(50) not NULL,
 `password` VARCHAR(50) not NULL,
 `admin` bool not null,
 `name` VARCHAR(50) not NULL,
 `image` VARCHAR(500) not NULL,
 `created_at` real not null,
 UNIQUE key `idx_email` (`email`),
 key `idx_created_at` (`created_at`),
 PRIMARY KEY (`id`)
) engine = innodb default charset=utf8;

create table blogs(
 `id` VARCHAR(50) not NULL,
 `user_id` VARCHAR(50) not NULL,
 `user_name` VARCHAR(50) not NULL,
 `user_image` VARCHAR(500) not NULL,
 `name` VARCHAR(50) not NULL,
 `summary` VARCHAR(50) not NULL,
 `content` bool not null,
 `created_at` real not null,
 key `idx_created_at` (`created_at`),
 PRIMARY KEY (`id`)
) engine = innodb default charset=utf8;

create table comments(
 `id` VARCHAR(50) not NULL,
 `blog_id` VARCHAR(50) not NULL,
 `user_id` VARCHAR(50) not NULL,
 `user_name` VARCHAR(50) not NULL,
 `user_image` VARCHAR(500) not NULL,
 `content` bool not null,
 `created_at` real not null,
 key `idx_created_at` (`created_at`),
 PRIMARY KEY (`id`)
) engine = innodb default charset=utf8;


-- email / password:
-- admin@example.com / password

insert into users (`id`, `email`, `password`, `admin`, `name`, `created_at`) values ('0010018336417540987fff4508f43fbaed718e263442526000', 'admin@example.com', '5f4dcc3b5aa765d61d8327deb882cf99', 1, 'Administrator', 1402909113.628);


