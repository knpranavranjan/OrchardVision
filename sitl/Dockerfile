# The real ArduPilot Copter flight code, built for Linux, running as a simulated vehicle.
# OrchardVision talks MAVLink to it exactly as it does to a Pixhawk.
FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sitl
RUN curl -fsSL -o arducopter \
        https://firmware.ardupilot.org/Copter/stable/SITL_x86_64_linux_gnu/arducopter \
    && chmod +x arducopter \
    && (curl -fsSL -o copter.parm \
        https://raw.githubusercontent.com/ArduPilot/ardupilot/ArduCopter-stable/Tools/autotest/default_params/copter.parm \
        || curl -fsSL -o copter.parm \
        https://raw.githubusercontent.com/ArduPilot/ardupilot/master/Tools/autotest/default_params/copter.parm)

# latitude,longitude,height above sea level,heading
ENV SITL_HOME=12.9716,77.5946,900,0
EXPOSE 5760

CMD ["sh", "-c", "./arducopter --model + --speedup 1 --defaults copter.parm --home ${SITL_HOME} -I0"]
