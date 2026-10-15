#import <Foundation/Foundation.h>
#import <IOKit/audio/IOAudioTypes.h>

#import <CoreMediaIO/CoreMediaIO.h>
#import <CoreVideo/CoreVideo.h>
#import <Security/Security.h>

static NSString *const CameraUID = @"C992D674-2E8B-49B5-97BC-F2BB28F648B0";
static const int Width = 640, Height = 480, FPS = 30;
@class Camera;

@interface Stream : NSObject <CMIOExtensionStreamSource>
@property CMIOExtensionStream *stream;
@property(weak) Camera *camera;
@property BOOL sink;
- (instancetype)initWithCamera:(Camera *)camera sink:(BOOL)sink;
@end

@interface Camera : NSObject <CMIOExtensionDeviceSource>
@property CMIOExtensionDevice *device;
@property Stream *output;
@property Stream *input;
@property NSArray<CMIOExtensionStreamFormat *> *formats;
@property CMIOExtensionClient *writer;
@property BOOL writing;
@property BOOL consuming;
@property NSUInteger generation;
@property NSUInteger readers;
@property dispatch_source_t timer;
@property(nonatomic) CVPixelBufferRef latest;
@property(nonatomic) CVPixelBufferRef blank;
@property(nonatomic) CMVideoFormatDescriptionRef format;
@property uint64_t lastFrameTime;
- (void)updateTimer;
- (void)clearWriter;
@end

static uint64_t hostTime(void) {
    return (uint64_t)(CMTimeGetSeconds(CMClockGetTime(CMClockGetHostTimeClock())) * 1e9);
}

// A signing identifier alone can be copied. Require the release Team ID too.
static BOOL trustedWriter(CMIOExtensionClient *client) {
    NSString *team = NSBundle.mainBundle.infoDictionary[@"YuzTeamID"];
    if (!team.length || [team isEqualToString:@"UNSIGNED"] ||
        ![client.signingID isEqualToString:@"com.yuzatolyesi.camera-bridge"]) return NO;
    NSDictionary *attributes = @{(__bridge NSString *)kSecGuestAttributePid: @(client.pid)};
    SecCodeRef code = NULL;
    if (SecCodeCopyGuestWithAttributes(NULL, (__bridge CFDictionaryRef)attributes,
                                      kSecCSDefaultFlags, &code) != errSecSuccess) return NO;
    NSString *rule = [NSString stringWithFormat:@"anchor apple generic and identifier \"com.yuzatolyesi.camera-bridge\" and certificate leaf[subject.OU] = \"%@\"", team];
    SecRequirementRef requirement = NULL;
    OSStatus status = SecRequirementCreateWithString((__bridge CFStringRef)rule, kSecCSDefaultFlags, &requirement);
    if (status == errSecSuccess) status = SecCodeCheckValidity(code, kSecCSDefaultFlags, requirement);
    if (requirement) CFRelease(requirement);
    CFRelease(code);
    return status == errSecSuccess;
}

@implementation Stream
- (instancetype)initWithCamera:(Camera *)camera sink:(BOOL)sink {
    if ((self = [super init])) {
        _camera = camera; _sink = sink;
        NSUUID *uid = [[NSUUID alloc] initWithUUIDString:sink ? @"85C8C8F4-34FC-447A-84FA-51DEAD199BD7" : @"35757FE8-BD7E-4C5C-92D9-796826209E90"];
        _stream = [[CMIOExtensionStream alloc] initWithLocalizedName:sink ? @"Yüz Atölyesi Girişi" : @"Yüz Atölyesi Kamera"
            streamID:uid direction:sink ? CMIOExtensionStreamDirectionSink : CMIOExtensionStreamDirectionSource
            clockType:CMIOExtensionStreamClockTypeHostTime source:self];
    }
    return self;
}
- (NSArray<CMIOExtensionStreamFormat *> *)formats { return self.camera.formats; }
- (NSSet<CMIOExtensionProperty> *)availableProperties {
    return [NSSet setWithArray:self.sink ? @[
        CMIOExtensionPropertyStreamActiveFormatIndex, CMIOExtensionPropertyStreamFrameDuration,
        CMIOExtensionPropertyStreamSinkBufferQueueSize, CMIOExtensionPropertyStreamSinkBuffersRequiredForStartup]
        : @[CMIOExtensionPropertyStreamActiveFormatIndex, CMIOExtensionPropertyStreamFrameDuration]];
}
- (CMIOExtensionStreamProperties *)streamPropertiesForProperties:(NSSet *)properties error:(NSError **)error {
    CMIOExtensionStreamProperties *result = [CMIOExtensionStreamProperties streamPropertiesWithDictionary:@{}];
    result.activeFormatIndex = @0;
    result.frameDuration = CFBridgingRelease(CMTimeCopyAsDictionary(CMTimeMake(1, FPS), kCFAllocatorDefault));
    if (self.sink) { result.sinkBufferQueueSize = @2; result.sinkBuffersRequiredForStartup = @1; }
    return result;
}
- (BOOL)setStreamProperties:(CMIOExtensionStreamProperties *)properties error:(NSError **)error {
    // Only the advertised format is supported; never accept an out-of-range index.
    if (properties.activeFormatIndex && properties.activeFormatIndex.intValue != 0) return NO;
    if (properties.frameDuration && CMTimeCompare(CMTimeMakeFromDictionary((__bridge CFDictionaryRef)properties.frameDuration), CMTimeMake(1, FPS))) return NO;
    return YES;
}
- (BOOL)authorizedToStartStreamForClient:(CMIOExtensionClient *)client {
    if (!self.sink) return YES;
    if (self.camera.writer || !trustedWriter(client)) return NO;
    self.camera.writer = client;
    return YES;
}
- (BOOL)startStreamAndReturnError:(NSError **)error {
    if (self.sink) {
        if (!self.camera.writer) return NO;
        self.camera.writing = YES;
    } else self.camera.readers += 1;
    [self.camera updateTimer];
    return YES;
}
- (BOOL)stopStreamAndReturnError:(NSError **)error {
    if (self.sink) [self.camera clearWriter];
    else if (self.camera.readers) self.camera.readers -= 1;
    [self.camera updateTimer];
    return YES;
}
@end

@implementation Camera
- (instancetype)init {
    if ((self = [super init])) {
        if (CMVideoFormatDescriptionCreate(kCFAllocatorDefault, kCVPixelFormatType_32BGRA, Width, Height, NULL, &_format) != noErr || !_format) return nil;
        CMIOExtensionStreamFormat *f = [[CMIOExtensionStreamFormat alloc] initWithFormatDescription:_format
            maxFrameDuration:CMTimeMake(1, FPS) minFrameDuration:CMTimeMake(1, FPS) validFrameDurations:nil];
        _formats = @[f];
        _device = [[CMIOExtensionDevice alloc] initWithLocalizedName:@"Yüz Atölyesi Kamera"
            deviceID:[[NSUUID alloc] initWithUUIDString:CameraUID] legacyDeviceID:CameraUID source:self];
        _output = [[Stream alloc] initWithCamera:self sink:NO];
        _input = [[Stream alloc] initWithCamera:self sink:YES];
        NSError *error;
        if (![_device addStream:_output.stream error:&error] || ![_device addStream:_input.stream error:&error]) return nil;
        NSDictionary *attributes = @{(__bridge NSString *)kCVPixelBufferIOSurfacePropertiesKey:@{}};
        if (CVPixelBufferCreate(kCFAllocatorDefault, Width, Height, kCVPixelFormatType_32BGRA,
                               (__bridge CFDictionaryRef)attributes, &_blank) != kCVReturnSuccess) return nil;
        CVPixelBufferLockBaseAddress(_blank, 0);
        memset(CVPixelBufferGetBaseAddress(_blank), 0, CVPixelBufferGetBytesPerRow(_blank) * Height);
        uint8_t *base = CVPixelBufferGetBaseAddress(_blank);
        size_t stride = CVPixelBufferGetBytesPerRow(_blank);
        for (int y = 0; y < Height; y++)
            for (int x = 0; x < Width; x++) base[y * stride + x * 4 + 3] = 255;
        CVPixelBufferUnlockBaseAddress(_blank, 0);
    }
    return self;
}
- (void)dealloc {
    if (_latest) CVPixelBufferRelease(_latest);
    if (_blank) CVPixelBufferRelease(_blank);
    if (_format) CFRelease(_format);
}
- (NSSet *)availableProperties { return [NSSet setWithArray:@[CMIOExtensionPropertyDeviceTransportType, CMIOExtensionPropertyDeviceModel]]; }
- (CMIOExtensionDeviceProperties *)devicePropertiesForProperties:(NSSet *)properties error:(NSError **)error {
    CMIOExtensionDeviceProperties *result = [CMIOExtensionDeviceProperties devicePropertiesWithDictionary:@{}];
    result.transportType = @(kIOAudioDeviceTransportTypeVirtual);
    result.model = @"Yüz Atölyesi Yerel Kamera";
    return result;
}
- (BOOL)setDeviceProperties:(CMIOExtensionDeviceProperties *)properties error:(NSError **)error { return YES; }
- (void)clearWriter {
    self.generation += 1; self.writing = NO; self.consuming = NO; self.writer = nil;
    if (_latest) { CVPixelBufferRelease(_latest); _latest = NULL; }
    self.lastFrameTime = 0;
}
- (void)tick {
    if (self.writing && self.writer && !self.consuming) {
        self.consuming = YES;
        NSUInteger generation = self.generation;
        [self.input.stream consumeSampleBufferFromClient:self.writer completionHandler:^(CMSampleBufferRef sample, uint64_t sequence, CMIOExtensionStreamDiscontinuityFlags flags, BOOL more, NSError *error) {
            if (sample) CFRetain(sample);
            dispatch_async(dispatch_get_main_queue(), ^{
                if (generation == self.generation) {
                    self.consuming = NO;
                    CVPixelBufferRef pixels = sample ? CMSampleBufferGetImageBuffer(sample) : NULL;
                    if (!error && pixels && CVPixelBufferGetWidth(pixels) == Width && CVPixelBufferGetHeight(pixels) == Height && CVPixelBufferGetPixelFormatType(pixels) == kCVPixelFormatType_32BGRA) {
                        if (self->_latest) CVPixelBufferRelease(self->_latest);
                        self->_latest = CVPixelBufferRetain(pixels);
                        self.lastFrameTime = hostTime();
                    }
                    if (sample) {
                        CMIOExtensionScheduledOutput *output = [[CMIOExtensionScheduledOutput alloc] initWithSequenceNumber:sequence hostTimeInNanoseconds:hostTime()];
                        [self.input.stream notifyScheduledOutputChanged:output];
                    }
                }
                if (sample) CFRelease(sample);
            });
        }];
    }
    if (!self.readers) return;
    uint64_t now = hostTime();
    // Never leave a person's last frame visible after the producer goes away.
    CVPixelBufferRef pixels = (_latest && now - self.lastFrameTime < 2000000000ULL) ? _latest : _blank;
    CMSampleTimingInfo timing = {CMTimeMake(1, FPS), CMTimeMake(now, 1000000000), kCMTimeInvalid};
    CMSampleBufferRef sample = NULL;
    if (CMSampleBufferCreateReadyWithImageBuffer(kCFAllocatorDefault, pixels, _format, &timing, &sample) == noErr) {
        [self.output.stream sendSampleBuffer:sample discontinuity:CMIOExtensionStreamDiscontinuityFlagNone hostTimeInNanoseconds:now];
        CFRelease(sample);
    }
}
- (void)updateTimer {
    if (!self.readers && !self.writing) {
        if (_timer) { dispatch_source_cancel(_timer); _timer = nil; }
        return;
    }
    if (_timer) return;
    _timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
    dispatch_source_set_timer(_timer, dispatch_time(DISPATCH_TIME_NOW, 0), NSEC_PER_SEC / FPS, NSEC_PER_MSEC);
    __weak Camera *weak = self;
    dispatch_source_set_event_handler(_timer, ^{ [weak tick]; });
    dispatch_resume(_timer);
}
@end

@interface Provider : NSObject <CMIOExtensionProviderSource>
@property CMIOExtensionProvider *provider;
@property Camera *camera;
@end
@implementation Provider
- (instancetype)init {
    if ((self = [super init])) {
        _provider = [[CMIOExtensionProvider alloc] initWithSource:self clientQueue:dispatch_get_main_queue()];
        _camera = [Camera new];
        if (!_camera || ![_provider addDevice:_camera.device error:nil]) return nil;
    }
    return self;
}
- (NSSet *)availableProperties { return [NSSet setWithObject:CMIOExtensionPropertyProviderManufacturer]; }
- (CMIOExtensionProviderProperties *)providerPropertiesForProperties:(NSSet *)properties error:(NSError **)error {
    CMIOExtensionProviderProperties *result = [CMIOExtensionProviderProperties providerPropertiesWithDictionary:@{}];
    result.manufacturer = @"Yüz Atölyesi";
    return result;
}
- (BOOL)setProviderProperties:(CMIOExtensionProviderProperties *)properties error:(NSError **)error { return YES; }
- (BOOL)connectClient:(CMIOExtensionClient *)client error:(NSError **)error { return YES; }
- (void)disconnectClient:(CMIOExtensionClient *)client {
    if ([self.camera.writer isEqual:client]) { [self.camera clearWriter]; [self.camera updateTimer]; }
}
@end

int main(void) {
    @autoreleasepool {
        Provider *source = [Provider new];
        if (!source) return 1;
        [CMIOExtensionProvider startServiceWithProvider:source.provider];
        CFRunLoopRun();
    }
    return 0;
}
