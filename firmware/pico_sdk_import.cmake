# Raspberry Pi Pico SDK Import Script
# This file provides standard SDK detection and bootstrap for Pico CMake projects.

if (DEFINED ENV{PICO_SDK_PATH} AND (NOT PICO_SDK_PATH))
    set(PICO_SDK_PATH $ENV{PICO_SDK_PATH})
    message(STATUS "PICO_SDK_PATH set from environment: ${PICO_SDK_PATH}")
endif ()

if (DEFINED PICO_SDK_PATH)
    # Check if SDK directory exists
    if (EXISTS "${PICO_SDK_PATH}/pico_sdk_init.cmake")
        message(STATUS "PICO_SDK found at: ${PICO_SDK_PATH}")
        include(${PICO_SDK_PATH}/pico_sdk_init.cmake)
    else()
        message(WARNING "Specified PICO_SDK_PATH was not valid: ${PICO_SDK_PATH}")
    endif()
else()
    message(STATUS "PICO_SDK_PATH is not set. Microcontroller build disabled; host simulation target enabled.")
endif ()
