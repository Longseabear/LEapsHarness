#pragma once

#include <cstdint>

#include "isp/bpc/bpc_config.h"

namespace isp::bpc {

struct ImagePlane {
    const uint16_t* input;
    uint16_t* output;
    int width;
    int height;
    int stride;
};

void CorrectBadPixels(const ImagePlane& plane, const BpcConfig& config);

}  // namespace isp::bpc
