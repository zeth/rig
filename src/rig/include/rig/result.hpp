#pragma once

#include <type_traits>
#include <utility>
#include <variant>

namespace rig {

template <int Status, typename Body>
struct error {
    static_assert(Status >= 400 && Status <= 599, "RIG error status must be 400 through 599");
    static constexpr int status = Status;
    Body body;
};

template <typename T>
struct is_error : std::false_type {};

template <int Status, typename Body>
struct is_error<error<Status, Body>> : std::true_type {};

template <typename Success, typename... Errors>
class result {
    static_assert(sizeof...(Errors) > 0, "RIG result requires at least one error");
    static_assert((is_error<Errors>::value && ...), "RIG result errors must be rig::error types");
    static_assert((!std::is_same_v<Success, Errors> && ...),
                  "RIG success and error types must differ");

public:
    result(Success value) : value_(std::move(value)) {}

    template <typename Error>
        requires ((std::is_same_v<std::remove_cvref_t<Error>, Errors> || ...))
    result(Error&& value) : value_(std::forward<Error>(value)) {}

    const std::variant<Success, Errors...>& value() const & { return value_; }

private:
    std::variant<Success, Errors...> value_;
};

} // namespace rig
