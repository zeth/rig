#include <dodger/game.hpp>
#include <build/dodger_routes.hpp>

#include <nlohmann/json.hpp>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <charconv>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {

using nlohmann::json;
using namespace std::chrono_literals;

struct HttpError : std::runtime_error {
    int status;
    HttpError(int status, const std::string& message)
        : std::runtime_error(message), status(status) {}
};

struct Request {
    std::string method;
    std::string path;
    std::string body;
};

Request read_request(int client) {
    std::string data;
    const std::size_t header_limit = 8192;
    const std::size_t body_limit = 4096;
    char buffer[1024];
    std::size_t header_end = std::string::npos;
    while ((header_end = data.find("\r\n\r\n")) == std::string::npos) {
        const auto count = recv(client, buffer, sizeof(buffer), 0);
        if (count <= 0) throw HttpError(400, "incomplete request");
        data.append(buffer, static_cast<std::size_t>(count));
        if (data.size() > header_limit) throw HttpError(413, "headers too large");
    }
    std::istringstream headers(data.substr(0, header_end));
    std::string line, version;
    Request request;
    if (!std::getline(headers, line) ||
        !(std::istringstream(line) >> request.method >> request.path >> version) ||
        (version != "HTTP/1.1\r" && version != "HTTP/1.0\r" &&
         version != "HTTP/1.1" && version != "HTTP/1.0"))
        throw HttpError(400, "invalid request line");

    std::size_t length = 0;
    bool has_length = false;
    while (std::getline(headers, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const auto colon = line.find(':');
        if (colon == std::string::npos) throw HttpError(400, "invalid header");
        auto key = line.substr(0, colon);
        std::transform(key.begin(), key.end(), key.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        auto value = line.substr(colon + 1);
        value.erase(0, value.find_first_not_of(' '));
        if (key == "transfer-encoding") throw HttpError(400, "chunked requests unsupported");
        if (key == "content-length") {
            if (has_length) throw HttpError(400, "duplicate content length");
            has_length = true;
            const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), length);
            if (error != std::errc{} || end != value.data() + value.size())
                throw HttpError(400, "invalid content length");
            if (length > body_limit) throw HttpError(413, "body too large");
        }
    }
    if (request.method == "POST" && !has_length)
        throw HttpError(411, "content length required");
    request.body = data.substr(header_end + 4);
    while (request.body.size() < length) {
        const auto count = recv(client, buffer, sizeof(buffer), 0);
        if (count <= 0) throw HttpError(400, "incomplete body");
        request.body.append(buffer, static_cast<std::size_t>(count));
    }
    request.body.resize(length);
    return request;
}

json dispatch(const Request& request) {
    try {
        if (auto response = rig_http::dispatch(request.method, request.path, request.body))
            return *response;
    } catch (const std::out_of_range&) {
        throw HttpError(404, "unknown game");
    } catch (const std::invalid_argument& error) {
        throw HttpError(400, error.what());
    } catch (const std::logic_error& error) {
        throw HttpError(409, error.what());
    }
    throw HttpError(404, "route not found");
}

void send_response(int client, int status, const json& body) {
    const char* reason = "OK";
    if (status == 400) reason = "Bad Request";
    if (status == 404) reason = "Not Found";
    if (status == 409) reason = "Conflict";
    if (status == 411) reason = "Length Required";
    if (status == 413) reason = "Content Too Large";
    if (status == 500) reason = "Internal Server Error";
    const auto payload = body.dump();
    const auto response = "HTTP/1.1 " + std::to_string(status) + " " + reason +
        "\r\nContent-Type: application/json\r\nContent-Length: " +
        std::to_string(payload.size()) + "\r\nConnection: close\r\n\r\n" + payload;
    std::size_t sent = 0;
    while (sent < response.size()) {
        const auto count = send(client, response.data() + sent, response.size() - sent, MSG_NOSIGNAL);
        if (count <= 0) return;
        sent += static_cast<std::size_t>(count);
    }
}

void handle_client(int client) {
    try {
        send_response(client, 200, dispatch(read_request(client)));
    } catch (const HttpError& error) {
        send_response(client, error.status, rig_json::encode(dodger::ErrorResponse{error.what()}));
    } catch (const std::exception& error) {
        std::cerr << "request failed: " << error.what() << '\n';
        send_response(client, 500, rig_json::encode(dodger::ErrorResponse{"internal server error"}));
    }
}

int listen_on(int port) {
    const int listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) throw std::runtime_error(std::strerror(errno));
    const int reuse = 1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(static_cast<std::uint16_t>(port));
    if (bind(listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 ||
        listen(listener, 8) != 0) {
        const auto message = std::string(std::strerror(errno));
        close(listener);
        throw std::runtime_error(message);
    }
    return listener;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const int port = argc == 2 ? std::stoi(argv[1]) : 8765;
        if (argc > 2 || port < 1 || port > 65535)
            throw std::invalid_argument("port must be 1 through 65535");
        const int listener = listen_on(port);
        std::cout << "Dodger listening on 127.0.0.1:" << port << std::endl;
        auto next_tick = std::chrono::steady_clock::now() + 33ms;
        while (true) {
            auto now = std::chrono::steady_clock::now();
            auto wait = std::chrono::duration_cast<std::chrono::microseconds>(
                std::max(0ns, next_tick - now));
            timeval timeout{static_cast<long>(wait.count() / 1000000),
                            static_cast<long>(wait.count() % 1000000)};
            fd_set incoming;
            FD_ZERO(&incoming);
            FD_SET(listener, &incoming);
            const int ready = select(listener + 1, &incoming, nullptr, nullptr, &timeout);
            if (ready < 0) {
                if (errno == EINTR) continue;
                throw std::runtime_error(std::strerror(errno));
            }
            if (ready > 0) {
                const int client = accept(listener, nullptr, nullptr);
                if (client >= 0) {
                    timeval receive_timeout{2, 0};
                    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO,
                               &receive_timeout, sizeof(receive_timeout));
                    handle_client(client);
                    close(client);
                }
            }
            now = std::chrono::steady_clock::now();
            while (now >= next_tick) {
                dodger::game_instance().tick();
                next_tick += 33ms;
            }
        }
    } catch (const std::exception& error) {
        std::cerr << "Dodger server: " << error.what() << '\n';
        return 1;
    }
}
