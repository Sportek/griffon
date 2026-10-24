package com.listings.api;

import org.springframework.boot.SpringApplication;

public class TestListingsApiApplication {

	public static void main(String[] args) {
		SpringApplication.from(ListingsApiApplication::main).with(TestcontainersConfiguration.class).run(args);
	}

}
