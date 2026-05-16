#pragma once

#include <cstdint>

namespace isp::bpc {

struct BpcConfig {
    int hot_threshold_q8;
    int cold_threshold_q8;
    bool enable_cross_check;
};

}  // namespace isp::bpc
