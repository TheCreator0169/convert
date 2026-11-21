// ConvertMenu.dll: IExplorerCommand for the Windows 11 top-level context menu entry "Convert".
// Hand-written COM, no WRL/wil/external libraries. Launches Convert.exe next to this DLL.
// Never runs a shell, never logs, never writes files.

#include <initguid.h>
#include <windows.h>
#include <shobjidl_core.h>
#include <shlwapi.h>
#include <objbase.h>
#include <cwchar>
#include <new>
#include <string>
#include <vector>

#include "exts.h"

// {6D1C2F3A-8B47-4E59-9A0C-3F5B7E21D4C8}
static const GUID kClsid = {0x6D1C2F3A, 0x8B47, 0x4E59, {0x9A, 0x0C, 0x3F, 0x5B, 0x7E, 0x21, 0xD4, 0xC8}};

static const wchar_t kExeName[] = L"Convert.exe";
static const size_t kMaxEnumState = 500;     // items inspected in GetState
static const size_t kMaxEnumInvoke = 2000;   // items inspected and paths collected in Invoke
static const size_t kMaxCmdChars = 30000;    // CreateProcessW limit is 32767 including the terminator
static const DWORD kMaxPathChars = 32767;

static HMODULE g_hModule = nullptr;
static volatile LONG g_objCount = 0;   // live COM objects and class factories
static volatile LONG g_lockCount = 0;  // LockServer calls

// Folder that holds this DLL, without a trailing backslash. Handles long paths.
static bool GetDllFolder(std::wstring& folder) {
    std::vector<wchar_t> buf(MAX_PATH);
    for (;;) {
        DWORD n = GetModuleFileNameW(g_hModule, buf.data(), static_cast<DWORD>(buf.size()));
        if (n == 0) return false;
        if (n < buf.size()) {  // not truncated
            std::wstring full(buf.data(), n);
            size_t pos = full.find_last_of(L'\\');
            if (pos == std::wstring::npos) return false;
            folder = full.substr(0, pos);
            return true;
        }
        if (buf.size() >= kMaxPathChars) return false;
        size_t next = buf.size() * 2;
        if (next > kMaxPathChars) next = kMaxPathChars;
        buf.resize(next);
    }
}

static bool GetConvertExePath(std::wstring& exe, std::wstring& dir) {
    if (!GetDllFolder(dir)) return false;
    exe = dir + L"\\" + kExeName;
    return true;
}

static bool ConvertExeExists(const std::wstring& exe) {
    DWORD attr = GetFileAttributesW(exe.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

// Case-insensitive match of the file extension against kExts (all lower-case, with dot).
static bool HasSupportedExtension(const wchar_t* path) {
    const wchar_t* ext = PathFindExtensionW(path);
    if (!ext || !*ext) return false;
    for (size_t i = 0; i < kExtCount; ++i) {
        if (_wcsicmp(ext, kExts[i]) == 0) return true;
    }
    return false;
}

// True when the item is a file system path that is not a folder. Writes the path to out.
static bool ItemFilePath(IShellItem* item, std::wstring& out) {
    SFGAOF attr = 0;
    if (SUCCEEDED(item->GetAttributes(SFGAO_FOLDER, &attr)) && (attr & SFGAO_FOLDER)) return false;

    LPWSTR path = nullptr;
    if (FAILED(item->GetDisplayName(SIGDN_FILESYSPATH, &path)) || !path) return false;
    out.assign(path);
    CoTaskMemFree(path);
    return !out.empty();
}

class CConvertMenu final : public IExplorerCommand {
public:
    CConvertMenu() : m_ref(1) { InterlockedIncrement(&g_objCount); }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IExplorerCommand)) {
            *ppv = static_cast<IExplorerCommand*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&m_ref));
    }
    STDMETHODIMP_(ULONG) Release() override {
        LONG r = InterlockedDecrement(&m_ref);
        if (r == 0) {
            delete this;
        }
        return static_cast<ULONG>(r);
    }

    // IExplorerCommand
    STDMETHODIMP GetTitle(IShellItemArray*, LPWSTR* ppszName) override {
        if (!ppszName) return E_POINTER;
        *ppszName = nullptr;
        return SHStrDupW(L"Convert", ppszName);
    }

    STDMETHODIMP GetIcon(IShellItemArray*, LPWSTR* ppszIcon) override {
        if (!ppszIcon) return E_POINTER;
        *ppszIcon = nullptr;
        std::wstring exe, dir;
        if (!GetConvertExePath(exe, dir)) return E_FAIL;
        std::wstring icon = exe + L",0";
        return SHStrDupW(icon.c_str(), ppszIcon);
    }

    STDMETHODIMP GetToolTip(IShellItemArray*, LPWSTR* ppszInfotip) override {
        if (!ppszInfotip) return E_POINTER;
        *ppszInfotip = nullptr;
        return E_NOTIMPL;
    }

    STDMETHODIMP GetCanonicalName(GUID* pguidCommandName) override {
        if (!pguidCommandName) return E_POINTER;
        *pguidCommandName = GUID{};  // GUID_NULL
        return S_OK;
    }

    STDMETHODIMP GetState(IShellItemArray* psiItemArray, BOOL, EXPCMDSTATE* pState) override {
        if (!pState) return E_POINTER;
        // The top-level menu can ask before a selection is set: show the entry then (Invoke still picks only supported files).
        if (!psiItemArray) { *pState = ECS_ENABLED; return S_OK; }
        *pState = ECS_HIDDEN;

        DWORD count = 0;
        if (FAILED(psiItemArray->GetCount(&count))) return S_OK;
        DWORD limit = count < kMaxEnumState ? count : static_cast<DWORD>(kMaxEnumState);
        if (count > limit) *pState = ECS_ENABLED;  // a huge selection: show the entry, Invoke picks the supported files
        for (DWORD i = 0; i < limit; ++i) {
            IShellItem* item = nullptr;
            if (FAILED(psiItemArray->GetItemAt(i, &item)) || !item) continue;
            std::wstring path;
            bool supported = ItemFilePath(item, path) && HasSupportedExtension(path.c_str());
            item->Release();
            if (supported) {
                *pState = ECS_ENABLED;
                break;
            }
        }
        return S_OK;
    }

    STDMETHODIMP Invoke(IShellItemArray* psiItemArray, IBindCtx*) override {
        std::wstring exe, dir;
        if (!GetConvertExePath(exe, dir)) return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
        if (!ConvertExeExists(exe)) return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
        if (!psiItemArray) return S_OK;

        std::vector<std::wstring> paths;
        DWORD count = 0;
        if (SUCCEEDED(psiItemArray->GetCount(&count))) {
            DWORD limit = count < kMaxEnumInvoke ? count : static_cast<DWORD>(kMaxEnumInvoke);
            for (DWORD i = 0; i < limit && paths.size() < kMaxEnumInvoke; ++i) {
                IShellItem* item = nullptr;
                if (FAILED(psiItemArray->GetItemAt(i, &item)) || !item) continue;
                std::wstring path;
                if (ItemFilePath(item, path) && HasSupportedExtension(path.c_str()) &&
                    path.find(L'"') == std::wstring::npos && path.back() != L'\\') {
                    paths.push_back(path);
                }
                item->Release();
            }
        }
        if (paths.empty()) return S_OK;

        // Batches of quoted arguments, each command line under kMaxCmdChars.
        const std::wstring quotedExe = L"\"" + exe + L"\"";
        std::wstring cmd = quotedExe;
        HRESULT hr = S_OK;
        bool pending = false;
        for (const std::wstring& p : paths) {
            size_t extra = p.size() + 3;  // space, two quotes
            if (quotedExe.size() + extra > kMaxCmdChars) continue;  // cannot fit even alone
            if (cmd.size() + extra > kMaxCmdChars) {
                HRESULT r = LaunchConvert(exe, dir, cmd);
                if (FAILED(r) && SUCCEEDED(hr)) hr = r;
                cmd = quotedExe;
            }
            cmd += L" \"" + p + L"\"";
            pending = true;
        }
        if (pending) {
            HRESULT r = LaunchConvert(exe, dir, cmd);
            if (FAILED(r) && SUCCEEDED(hr)) hr = r;
        }
        return hr;
    }

    STDMETHODIMP GetFlags(EXPCMDFLAGS* pFlags) override {
        if (!pFlags) return E_POINTER;
        *pFlags = ECF_DEFAULT;
        return S_OK;
    }

    STDMETHODIMP EnumSubCommands(IEnumExplorerCommand** ppEnum) override {
        if (!ppEnum) return E_POINTER;
        *ppEnum = nullptr;
        return E_NOTIMPL;
    }

private:
    ~CConvertMenu() { InterlockedDecrement(&g_objCount); }

    static HRESULT LaunchConvert(const std::wstring& exe, const std::wstring& dir, const std::wstring& cmd) {
        std::vector<wchar_t> buf(cmd.begin(), cmd.end());
        buf.push_back(L'\0');

        STARTUPINFOW si = {};
        si.cb = sizeof(si);
        PROCESS_INFORMATION pi = {};
        if (!CreateProcessW(exe.c_str(), buf.data(), nullptr, nullptr, FALSE, 0, nullptr, dir.c_str(), &si, &pi)) {
            return HRESULT_FROM_WIN32(GetLastError());
        }
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return S_OK;
    }

    volatile LONG m_ref;
};

class CClassFactory final : public IClassFactory {
public:
    CClassFactory() : m_ref(1) { InterlockedIncrement(&g_objCount); }

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IClassFactory)) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override {
        return static_cast<ULONG>(InterlockedIncrement(&m_ref));
    }
    STDMETHODIMP_(ULONG) Release() override {
        LONG r = InterlockedDecrement(&m_ref);
        if (r == 0) {
            delete this;
        }
        return static_cast<ULONG>(r);
    }

    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;
        CConvertMenu* obj = new (std::nothrow) CConvertMenu();
        if (!obj) return E_OUTOFMEMORY;
        HRESULT hr = obj->QueryInterface(riid, ppv);
        obj->Release();
        return hr;
    }

    STDMETHODIMP LockServer(BOOL fLock) override {
        if (fLock) {
            InterlockedIncrement(&g_lockCount);
        } else {
            InterlockedDecrement(&g_lockCount);
        }
        return S_OK;
    }

private:
    ~CClassFactory() { InterlockedDecrement(&g_objCount); }

    volatile LONG m_ref;
};

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_hModule = hinst;
        DisableThreadLibraryCalls(hinst);
    }
    return TRUE;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    if (!IsEqualCLSID(rclsid, kClsid)) return CLASS_E_CLASSNOTAVAILABLE;
    CClassFactory* factory = new (std::nothrow) CClassFactory();
    if (!factory) return E_OUTOFMEMORY;
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

STDAPI DllCanUnloadNow(void) {
    return (g_objCount == 0 && g_lockCount == 0) ? S_OK : S_FALSE;
}
