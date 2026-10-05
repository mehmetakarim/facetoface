#include "pch.h"
#include "WinTrace.h"
#include "SharedFrames.h"

#define FRAME_HEADER_SIZE 32
#define STATE_READY 2
#define STALE_NS 1500000000ULL // older frames mean the engine stopped or hung

static size_t Align32(size_t size)
{
	return (size + 31) & ~(size_t)31;
}

size_t SharedFrames::MappingSize()
{
	size_t frame = (size_t)YUZ_FRAME_WIDTH * YUZ_FRAME_HEIGHT * 3 / 2;
	size_t size = Align32(sizeof(QueueHeader));
	for (int i = 0; i < 3; i++)
	{
		size = Align32(size + FRAME_HEADER_SIZE + frame);
	}
	return size;
}

// Same clock as Python's time.monotonic_ns() on Windows (QueryPerformanceCounter).
static uint64_t MonotonicNs()
{
	LARGE_INTEGER counter, frequency;
	QueryPerformanceCounter(&counter);
	QueryPerformanceFrequency(&frequency);
	auto seconds = (uint64_t)counter.QuadPart / frequency.QuadPart;
	auto remainder = (uint64_t)counter.QuadPart % frequency.QuadPart;
	return seconds * 1000000000ULL + remainder * 1000000000ULL / frequency.QuadPart;
}

bool SharedFrames::Ensure()
{
	if (_view)
		return true;

	// Retrying costs a kernel call; once a second is plenty while nothing is published.
	auto now = GetTickCount64();
	if (_lastAttempt && now - _lastAttempt < 1000)
		return false;
	_lastAttempt = now;

	auto size = MappingSize();
	// Only the interactive user, services and administrators may touch the frames.
	PSECURITY_DESCRIPTOR descriptor = nullptr;
	SECURITY_ATTRIBUTES attributes{ sizeof(attributes), nullptr, FALSE };
	if (ConvertStringSecurityDescriptorToSecurityDescriptorW(L"D:P(A;;GA;;;SY)(A;;GA;;;LS)(A;;GA;;;BA)(A;;GA;;;IU)",
		SDDL_REVISION_1, &descriptor, nullptr))
	{
		attributes.lpSecurityDescriptor = descriptor;
	}

	_mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, &attributes, PAGE_READWRITE,
		(DWORD)((uint64_t)size >> 32), (DWORD)size, YUZ_SHARED_NAME);
	if (descriptor)
	{
		LocalFree(descriptor);
	}

	// Processes without the "create global objects" right can still read an existing mapping.
	if (!_mapping)
	{
		_mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, YUZ_SHARED_NAME);
	}
	if (!_mapping)
	{
		WINTRACE(L"SharedFrames mapping unavailable: %u", GetLastError());
		return false;
	}

	_view = (BYTE*)MapViewOfFile(_mapping, FILE_MAP_READ, 0, 0, size);
	if (!_view)
	{
		CloseHandle(_mapping);
		_mapping = nullptr;
		return false;
	}
	WINTRACE(L"SharedFrames mapped %Iu bytes", size);
	return true;
}

SharedFrames::~SharedFrames()
{
	if (_view)
	{
		UnmapViewOfFile(_view);
	}
	if (_mapping)
	{
		CloseHandle(_mapping);
	}
}

bool SharedFrames::CopyLatest(BYTE* scanline, LONG pitch, UINT width, UINT height)
{
	if (!scanline || pitch < (LONG)width || !Ensure())
		return false;

	auto header = (QueueHeader*)_view;
	if (header->state != STATE_READY || header->cx != width || header->cy != height)
		return false;

	auto index = header->read_idx % 3;
	auto offset = (size_t)header->offsets[index];
	auto frame = (size_t)width * height * 3 / 2;
	if (offset < sizeof(QueueHeader) || offset + FRAME_HEADER_SIZE + frame > MappingSize())
		return false;

	auto timestamp = *(volatile uint64_t*)(_view + offset);
	auto now = MonotonicNs();
	if (timestamp > now || now - timestamp > STALE_NS)
		return false;

	// NV12: full-size Y plane, then interleaved UV at half height; the MF buffer may pad rows.
	auto source = _view + offset + FRAME_HEADER_SIZE;
	for (UINT y = 0; y < height; y++)
	{
		memcpy(scanline + (size_t)y * pitch, source + (size_t)y * width, width);
	}
	auto uv = source + (size_t)width * height;
	for (UINT y = 0; y < height / 2; y++)
	{
		memcpy(scanline + (size_t)(height + y) * pitch, uv + (size_t)y * width, width);
	}
	return true;
}
