#import <Foundation/Foundation.h>
#import <CoreMediaIO/CoreMediaIO.h>
#import <CoreVideo/CoreVideo.h>
#include <unistd.h>
#include <errno.h>
#include <vector>

static const int Width = 640, Height = 480;
static const size_t FrameBytes = Width * Height * 4;
static CFStringRef CameraUID = CFSTR("C992D674-2E8B-49B5-97BC-F2BB28F648B0");

static std::vector<CMIOObjectID> objects(CMIOObjectID object, CMIOObjectPropertySelector selector, CMIOObjectPropertyScope scope) {
    CMIOObjectPropertyAddress address = {selector, scope, kCMIOObjectPropertyElementMain};
    UInt32 bytes = 0;
    if (CMIOObjectGetPropertyDataSize(object, &address, 0, NULL, &bytes) != noErr || bytes % sizeof(CMIOObjectID)) return {};
    std::vector<CMIOObjectID> result(bytes / sizeof(CMIOObjectID));
    if (bytes && CMIOObjectGetPropertyData(object, &address, 0, NULL, bytes, &bytes, result.data()) != noErr) return {};
    result.resize(bytes / sizeof(CMIOObjectID));
    return result;
}
static CMIODeviceID findDevice(void) {
    for (auto device : objects(kCMIOObjectSystemObject, kCMIOHardwarePropertyDevices, kCMIOObjectPropertyScopeGlobal)) {
        CMIOObjectPropertyAddress address = {kCMIODevicePropertyDeviceUID, kCMIOObjectPropertyScopeGlobal, kCMIOObjectPropertyElementMain};
        CFStringRef uid = NULL; UInt32 bytes = sizeof(uid);
        if (CMIOObjectGetPropertyData(device, &address, 0, NULL, bytes, &bytes, &uid) == noErr && uid) {
            bool match = CFEqual(uid, CameraUID); CFRelease(uid);
            if (match) return device;
        }
    }
    return 0;
}
static CMSampleBufferRef makeSample(const uint8_t *bytes) {
    CVPixelBufferRef pixels = NULL;
    NSDictionary *attributes = @{(__bridge NSString *)kCVPixelBufferIOSurfacePropertiesKey:@{}};
    if (CVPixelBufferCreate(kCFAllocatorDefault, Width, Height, kCVPixelFormatType_32BGRA,
                           (__bridge CFDictionaryRef)attributes, &pixels) != kCVReturnSuccess) return NULL;
    CVPixelBufferLockBaseAddress(pixels, 0);
    size_t stride = CVPixelBufferGetBytesPerRow(pixels);
    for (int row = 0; row < Height; row++) memcpy((uint8_t *)CVPixelBufferGetBaseAddress(pixels) + row * stride, bytes + row * Width * 4, Width * 4);
    CVPixelBufferUnlockBaseAddress(pixels, 0);
    CMVideoFormatDescriptionRef format = NULL;
    CMSampleBufferRef sample = NULL;
    if (CMVideoFormatDescriptionCreateForImageBuffer(kCFAllocatorDefault, pixels, &format) == noErr) {
        CMSampleTimingInfo timing = {CMTimeMake(1, 30), CMClockGetTime(CMClockGetHostTimeClock()), kCMTimeInvalid};
        CMSampleBufferCreateReadyWithImageBuffer(kCFAllocatorDefault, pixels, format, &timing, &sample);
        CFRelease(format);
    }
    CVPixelBufferRelease(pixels);
    return sample;
}
static int selfTest(void) {
    std::vector<uint8_t> bytes(FrameBytes, 0);
    for (size_t i = 0; i < FrameBytes; i += 4) { bytes[i] = 23; bytes[i+1] = 97; bytes[i+2] = 201; bytes[i+3] = 255; }
    CMSampleBufferRef sample = makeSample(bytes.data());
    if (!sample) return 1;
    CVPixelBufferRef pixels = CMSampleBufferGetImageBuffer(sample);
    CVPixelBufferLockBaseAddress(pixels, kCVPixelBufferLock_ReadOnly);
    bool valid = CVPixelBufferGetWidth(pixels) == Width && CVPixelBufferGetHeight(pixels) == Height;
    for (int row = 0; row < Height && valid; row++) valid = memcmp((uint8_t *)CVPixelBufferGetBaseAddress(pixels) + row * CVPixelBufferGetBytesPerRow(pixels), bytes.data()+row*Width*4, Width*4) == 0;
    CVPixelBufferUnlockBaseAddress(pixels, kCVPixelBufferLock_ReadOnly);
    CFRelease(sample);
    puts(valid ? "PASS: BGRA rows, format and sample buffer" : "FAIL");
    return valid ? 0 : 1;
}
int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return selfTest();
        if (argc != 2 || (strcmp(argv[1], "--status") && strcmp(argv[1], "--send"))) return 2;
        CMIODeviceID device = findDevice();
        auto streams = device ? objects(device, kCMIODevicePropertyStreams, kCMIODevicePropertyScopeOutput) : std::vector<CMIOObjectID>{};
        if (!strcmp(argv[1], "--status")) { puts(device && !streams.empty() ? "{\"installed\":true}" : "{\"installed\":false}"); return 0; }
        if (!device || streams.size() != 1) { fprintf(stderr, "Yüz Atölyesi Kamera uzantısı etkin değil.\n"); return 3; }
        CMSimpleQueueRef queue = NULL;
        if (CMIOStreamCopyBufferQueue(streams[0], NULL, NULL, &queue) != noErr || !queue) return 4;
        if (CMIODeviceStartStream(device, streams[0]) != noErr) { CFRelease(queue); return 5; }
        puts("READY"); fflush(stdout);
        std::vector<uint8_t> bytes(FrameBytes);
        int result = 0;
        while (true) {
            size_t count = 0;
            while (count < FrameBytes) {
                ssize_t amount = read(STDIN_FILENO, bytes.data() + count, FrameBytes - count);
                if (amount < 0 && errno == EINTR) continue;
                if (amount <= 0) break;
                count += amount;
            }
            if (!count) break;
            if (count != FrameBytes) { result = 6; break; }
            // Bounded queue: discard under backpressure rather than delay the engine.
            if (CMSimpleQueueGetFullness(queue) >= 1.0) continue;
            CMSampleBufferRef sample = makeSample(bytes.data());
            if (!sample) { result = 7; break; }
            if (CMSimpleQueueEnqueue(queue, sample) != noErr) CFRelease(sample);
            // Successful enqueue transfers the retained sample to CMIO.
        }
        CMIODeviceStopStream(device, streams[0]);
        CFRelease(queue);
        return result;
    }
}
