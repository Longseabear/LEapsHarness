#include "isp/bpc/bpc.h"

#include <array>
#include <cassert>

int main() {
    std::array<uint16_t, 9> input = {10, 10, 10, 10, 255, 10, 10, 10, 10};
    std::array<uint16_t, 9> output = {};
    isp::bpc::ImagePlane plane{input.data(), output.data(), 3, 3, 3};
    isp::bpc::BpcConfig config{64 << 8, 64 << 8, true};
    isp::bpc::CorrectBadPixels(plane, config);
    assert(output[4] == 10);
    return 0;
}
