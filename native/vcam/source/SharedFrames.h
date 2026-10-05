#pragma once

// Reads NV12 frames that the Yüz Atölyesi engine publishes to shared memory.
// Layout matches engine/virtualcam.py (itself the OBS virtual camera queue):
// a header followed by three frame slots, each starting with a timestamp.
// The media source runs inside the Frame Server service, which may create
// objects in the Global namespace; the engine (a normal user process) cannot,
// so the source creates the mapping and the engine only opens it.

#define YUZ_SHARED_NAME L"Global\\YuzAtolyesiKamera"
#define YUZ_FRAME_WIDTH 1280
#define YUZ_FRAME_HEIGHT 960

struct QueueHeader
{
	volatile uint32_t write_idx;
	volatile uint32_t read_idx;
	volatile uint32_t state;
	uint32_t offsets[3];
	uint32_t type;
	uint32_t cx;
	uint32_t cy;
	uint64_t interval;
	uint32_t reserved[8];
};
static_assert(sizeof(QueueHeader) == 80, "must match engine/virtualcam.py HEADER");

class SharedFrames
{
	HANDLE _mapping;
	BYTE* _view;
	ULONGLONG _lastAttempt;

	bool Ensure();

public:
	SharedFrames() : _mapping(nullptr), _view(nullptr), _lastAttempt(0) {}
	~SharedFrames();

	static size_t MappingSize();
	// Copies the newest fresh frame into an NV12 buffer; false means show the placeholder.
	bool CopyLatest(BYTE* scanline, LONG pitch, UINT width, UINT height);
};
