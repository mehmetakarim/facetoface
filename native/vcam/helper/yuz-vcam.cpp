// Keeps the "Yüz Atölyesi Kamera" virtual camera registered for as long as it runs.
//
// The engine starts this helper for a live job and holds its stdin open. When the
// engine stops, crashes or is killed, stdin closes and the camera is removed. A
// session-lifetime camera also disappears if this process is killed outright.
//
// Exit codes: 0 stopped normally, 2 Media Foundation unavailable, 3 camera could
// not be created (pre-Windows 11), 4 media source not installed, 5 start failed.
#include <windows.h>
#include <mfapi.h>
#include <mfvirtualcamera.h>
#include <cstdio>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfsensorgroup.lib")

// Must match CLSID_VCam in native/vcam/source/dllmain.cpp.
static const wchar_t SOURCE_CLSID[] = L"{92966083-168A-4874-9B2F-4E4F50BD7742}";
static const wchar_t CAMERA_NAME[] = L"Yüz Atölyesi Kamera";

static int Fail(int code, const char* step, HRESULT hr)
{
	printf("error %s 0x%08lX\n", step, (unsigned long)hr);
	fflush(stdout);
	return code;
}

int wmain()
{
	HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
	if (FAILED(hr))
		return Fail(2, "com", hr);
	hr = MFStartup(MF_VERSION);
	if (FAILED(hr))
		return Fail(2, "startup", hr);

	IMFVirtualCamera* camera = nullptr;
	hr = MFCreateVirtualCamera(MFVirtualCameraType_SoftwareCameraSource, MFVirtualCameraLifetime_Session,
		MFVirtualCameraAccess_CurrentUser, CAMERA_NAME, SOURCE_CLSID, nullptr, 0, &camera);
	if (FAILED(hr))
		return Fail(3, "create", hr);

	hr = camera->Start(nullptr);
	if (FAILED(hr))
	{
		camera->Remove();
		camera->Release();
		return Fail(hr == REGDB_E_CLASSNOTREG ? 4 : 5, "start", hr);
	}
	printf("ready\n");
	fflush(stdout);

	char line[64];
	while (fgets(line, sizeof(line), stdin))
	{
	}

	// Remove (not Shutdown): Shutdown would stop the source twice and keep the device listed.
	camera->Remove();
	camera->Release();
	MFShutdown();
	CoUninitialize();
	return 0;
}
