cmake_minimum_required(VERSION 3.13)

# Initialize Pico SDK
include(pico_sdk_import.cmake)

project(bamboo_firmware C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize Pico SDK environment if present
if (DEFINED PICO_SDK_PATH AND EXISTS "${PICO_SDK_PATH}/pico_sdk_init.cmake")
    pico_sdk_init()

    add_executable(bamboo_node
        src/main.c
        src/manchester.c
    )

    # Generate C header from PIO assembly
    pico_generate_pio_header(bamboo_node ${CMAKE_CURRENT_LIST_DIR}/src/manchester.pio)

    target_include_directories(bamboo_node PRIVATE
        include
        ${CMAKE_CURRENT_LIST_DIR}/../proto/c
    )

    target_compile_definitions(bamboo_node PRIVATE
        PICO_BOARD=1
    )

    target_link_libraries(bamboo_node
        pico_stdlib
        hardware_timer
        hardware_gpio
        hardware_pio
        hardware_uart
    )

    # Automatically generate .uf2, .hex, .bin, and .dis disassembly
    pico_add_extra_outputs(bamboo_node)
else()
    message(STATUS "PICO_SDK_PATH not set or invalid. Building host simulation target.")
    add_executable(bamboo_node_sim
        src/main.c
        src/manchester.c
    )
    target_include_directories(bamboo_node_sim PRIVATE
        include
        ${CMAKE_CURRENT_LIST_DIR}/../proto/c
    )
endif()
