JAVA_HOME ?= /opt/java/openjdk
CC ?= gcc
CFLAGS ?= -O1 -g -Wall -Wextra -fPIC
MVN_FLAGS ?= -B -q
SOURCES := native/attest.c native/jni_attest.c

.PHONY: all native jar clean

all: native jar

native: build/libattest.so

build/libattest.so: $(SOURCES) native/attest.h
	mkdir -p build
	$(CC) $(CFLAGS) -shared -I$(JAVA_HOME)/include -I$(JAVA_HOME)/include/linux \
		-o build/libattest.so $(SOURCES)

jar: build/sentinel.jar

build/sentinel.jar: pom.xml $(shell find src -name '*.java')
	mkdir -p build
	mvn $(MVN_FLAGS) package
	cp target/sentinel.jar build/sentinel.jar

clean:
	rm -rf build target
