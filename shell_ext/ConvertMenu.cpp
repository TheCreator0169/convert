// ConvertMenu.dll: IExplorerCommand for the Windows 11 top-level context menu entry "Convert".
// Hand-written COM, no WRL/wil/external libraries. Launches Convert.exe next to this DLL.
// The entry is a flyout: "Convert to <label>" for the quick targets of the selected file type (quick.h), then a
// separator, then "Open Convert...". Never runs a shell, never logs, never writes files.

#include <initguid.h>
#include <windows.h>
#include <shobjidl_core.h>
#include <shlwapi.h>
#include <objbase.h>
#include <algorithm>
#include <cwchar>
#include <cwctype>
#include <new>
#include <string>
#include <utility>
#include <vector>

#include "exts.h"  // includes quick.h (generated)

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

enum class SubKind { Quick, Open, Separator };

// What one entry of the flyout shows and does.
struct SubItem {
    SubKind kind;
    std::wstring title;
    std::wstring fmtId;  // Quick entries only: the --quick argument
};

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

// Index into kExts of the path's extension (case-insensitive), or -1 when the type is not supported.
static int FindExt(const wchar_t* path) {
    const wchar_t* ext = PathFindExtensionW(path);
    if (!ext || !*ext) return -1;
    for (size_t i = 0; i < kExtCount; ++i) {
        if (_wcsicmp(ext, kExts[i]) == 0) return static_cast<int>(i);
    }
    return -1;
}

// Lower-case extension with its dot, aliases folded to the id's extension (jpeg->jpg, tif->tiff, aif->aiff, htm->html).
static std::wstring NormalizedExt(const wchar_t* path) {
    std::wstring e;
    const wchar_t* ext = PathFindExtensionW(path);
    for (const wchar_t* p = ext; p && *p; ++p) e.push_back(static_cast<wchar_t>(towlower(*p)));
    if (e == L".jpeg") return L".jpg";
    if (e == L".tif") return L".tiff";
    if (e == L".aif") return L".aiff";
    if (e == L".htm") return L".html";
    return e;
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

// Quick type of a selection: audio when it mixes audio and video, else the one type, else -1 (none).
// mask has one bit per QuickType.
static int SelectionType(unsigned mask) {
    const unsigned audio = 1u << kQuickAudio;
    const unsigned video = 1u << kQuickVideo;
    if (mask == (audio | video)) return kQuickAudio;
    for (int t = 0; t < kQuickTypeCount; ++t) {
        if (mask == (1u << t)) return t;
    }
    return -1;
}

// The flyout entries for a remembered selection: "Convert to <label>" per quick target of its type, except the
// target that every selected file already has; then a separator. Empty when nothing is remembered.
static std::vector<SubItem> QuickItems(unsigned mask, const std::vector<std::wstring>& exts) {
    std::vector<SubItem> items;
    const int type = SelectionType(mask);
    if (type < 0) return items;
    const QuickFmt* list = kQuickLists[type];
    const size_t n = kQuickCounts[type];
    const bool single = exts.size() == 1;
    for (size_t i = 0; i < n; ++i) {
        const std::wstring ext = std::wstring(L".") + list[i].ext;
        if (single && exts[0] == ext) continue;
        items.push_back(SubItem{SubKind::Quick, std::wstring(L"Convert to ") + list[i].label, list[i].id});
    }
    if (!items.empty()) items.push_back(SubItem{SubKind::Separator, std::wstring(), std::wstring()});
    return items;
}

// Starts Convert.exe with cmd. Does not wait for it.
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

// Supported file paths of the selection, with the same limits and rejects for every command.
static void CollectPaths(IShellItemArray* psi, std::vector<std::wstring>& paths) {
    DWORD count = 0;
    if (FAILED(psi->GetCount(&count))) return;
    DWORD limit = count < kMaxEnumInvoke ? count : static_cast<DWORD>(kMaxEnumInvoke);
    for (DWORD i = 0; i < limit && paths.size() < kMaxEnumInvoke; ++i) {
        IShellItem* item = nullptr;
        if (FAILED(psi->GetItemAt(i, &item)) || !item) continue;
        std::wstring path;
        if (ItemFilePath(item, path) && FindExt(path.c_str()) >= 0 &&
            path.find(L'"') == std::wstring::npos && path.back() != L'\\') {
            paths.push_back(path);
        }
        item->Release();
    }
}

// Launches Convert.exe for the supported files of the selection: "<exe> --quick <id> <files>" when quickId is set,
// else "<exe> <files>" (opens the window).
static HRESULT InvokeConvert(IShellItemArray* psi, const std::wstring& quickId) {
    std::wstring exe, dir;
    if (!GetConvertExePath(exe, dir)) return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
    if (!ConvertExeExists(exe)) return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
    if (!psi) return S_OK;

    std::vector<std::wstring> paths;
    CollectPaths(psi, paths);
    if (paths.empty()) return S_OK;

    // Batches of quoted arguments; every command line starts with prefix and stays under kMaxCmdChars.
    std::wstring prefix = L"\"" + exe + L"\"";
    if (!quickId.empty()) prefix += L" --quick " + quickId;
    std::wstring cmd = prefix;
    HRESULT hr = S_OK;
    bool pending = false;
    for (const std::wstring& p : paths) {
        size_t extra = p.size() + 3;  // space, two quotes
        if (prefix.size() + extra > kMaxCmdChars) continue;  // cannot fit even alone
        if (cmd.size() + extra > kMaxCmdChars) {
            HRESULT r = LaunchConvert(exe, dir, cmd);
            if (FAILED(r) && SUCCEEDED(hr)) hr = r;
            cmd = prefix;
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

// Icon text shared by the top-level entry and its sub-commands.
static HRESULT ConvertIconText(LPWSTR* ppszIcon) {
    std::wstring exe, dir;
    if (!GetConvertExePath(exe, dir)) return E_FAIL;
    std::wstring icon = exe + L",0";
    return SHStrDupW(icon.c_str(), ppszIcon);
}

// One entry of the flyout ("Convert to <label>", the separator, or "Open Convert...").
class CConvertSub final : public IExplorerCommand {
public:
    explicit CConvertSub(SubItem item) : m_item(std::move(item)), m_ref(1) { InterlockedIncrement(&g_objCount); }

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
        if (m_item.kind == SubKind::Separator) return E_NOTIMPL;
        return SHStrDupW(m_item.title.c_str(), ppszName);
    }

    STDMETHODIMP GetIcon(IShellItemArray*, LPWSTR* ppszIcon) override {
        if (!ppszIcon) return E_POINTER;
        *ppszIcon = nullptr;
        if (m_item.kind == SubKind::Separator) return E_NOTIMPL;
        return ConvertIconText(ppszIcon);
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

    STDMETHODIMP GetState(IShellItemArray*, BOOL, EXPCMDSTATE* pState) override {
        if (!pState) return E_POINTER;
        *pState = ECS_ENABLED;
        if (m_item.kind == SubKind::Separator) return E_NOTIMPL;
        return S_OK;
    }

    STDMETHODIMP Invoke(IShellItemArray* psiItemArray, IBindCtx*) override {
        if (m_item.kind == SubKind::Separator) return E_NOTIMPL;
        return InvokeConvert(psiItemArray, m_item.kind == SubKind::Quick ? m_item.fmtId : std::wstring());
    }

    STDMETHODIMP GetFlags(EXPCMDFLAGS* pFlags) override {
        if (!pFlags) return E_POINTER;
        *pFlags = m_item.kind == SubKind::Separator ? ECF_ISSEPARATOR : ECF_DEFAULT;
        return S_OK;
    }

    STDMETHODIMP EnumSubCommands(IEnumExplorerCommand** ppEnum) override {
        if (!ppEnum) return E_POINTER;
        *ppEnum = nullptr;
        return E_NOTIMPL;
    }

private:
    ~CConvertSub() { InterlockedDecrement(&g_objCount); }

    const SubItem m_item;
    volatile LONG m_ref;
};

// IEnumExplorerCommand over a copy of the flyout entries. Creates a CConvertSub per entry handed out.
class CEnumSub final : public IEnumExplorerCommand {
public:
    explicit CEnumSub(std::vector<SubItem> items) : m_items(std::move(items)), m_next(0), m_ref(1) {
        InterlockedIncrement(&g_objCount);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IEnumExplorerCommand)) {
            *ppv = static_cast<IEnumExplorerCommand*>(this);
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

    // IEnumExplorerCommand
    STDMETHODIMP Next(ULONG celt, IExplorerCommand** rgelt, ULONG* pceltFetched) override {
        if (pceltFetched) *pceltFetched = 0;
        if (!rgelt && celt) return E_POINTER;
        if (!pceltFetched && celt != 1) return E_INVALIDARG;
        ULONG fetched = 0;
        while (fetched < celt && m_next < m_items.size()) {
            CConvertSub* cmd = new (std::nothrow) CConvertSub(m_items[m_next]);
            if (!cmd) break;
            rgelt[fetched++] = cmd;  // the reference from new goes to the caller
            ++m_next;
        }
        if (pceltFetched) *pceltFetched = fetched;
        return fetched == celt ? S_OK : S_FALSE;
    }

    STDMETHODIMP Skip(ULONG celt) override {
        size_t left = m_items.size() - m_next;
        if (celt > left) {
            m_next = m_items.size();
            return S_FALSE;
        }
        m_next += celt;
        return S_OK;
    }

    STDMETHODIMP Reset() override {
        m_next = 0;
        return S_OK;
    }

    STDMETHODIMP Clone(IEnumExplorerCommand** ppenum) override {
        if (!ppenum) return E_POINTER;
        *ppenum = nullptr;
        CEnumSub* copy = new (std::nothrow) CEnumSub(m_items);
        if (!copy) return E_OUTOFMEMORY;
        copy->m_next = m_next;
        HRESULT hr = copy->QueryInterface(IID_IEnumExplorerCommand, reinterpret_cast<void**>(ppenum));
        copy->Release();
        return hr;
    }

private:
    ~CEnumSub() { InterlockedDecrement(&g_objCount); }

    std::vector<SubItem> m_items;
    size_t m_next;
    volatile LONG m_ref;
};

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
        return ConvertIconText(ppszIcon);
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
        // Remember the selection for EnumSubCommands: copies only, never the IShellItemArray.
        m_typeMask = 0;
        m_exts.clear();
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
            if (ItemFilePath(item, path)) {
                int idx = FindExt(path.c_str());
                if (idx >= 0) {
                    *pState = ECS_ENABLED;
                    Remember(idx, path);
                }
            }
            item->Release();
        }
        // A partial view of a huge selection does not give its type: no quick targets then.
        if (count > limit) { m_typeMask = 0; m_exts.clear(); }
        return S_OK;
    }

    STDMETHODIMP Invoke(IShellItemArray* psiItemArray, IBindCtx*) override {
        return InvokeConvert(psiItemArray, std::wstring());
    }

    STDMETHODIMP GetFlags(EXPCMDFLAGS* pFlags) override {
        if (!pFlags) return E_POINTER;
        *pFlags = ECF_HASSUBCOMMANDS;
        return S_OK;
    }

    STDMETHODIMP EnumSubCommands(IEnumExplorerCommand** ppEnum) override {
        if (!ppEnum) return E_POINTER;
        *ppEnum = nullptr;
        std::vector<SubItem> items = QuickItems(m_typeMask, m_exts);
        items.push_back(SubItem{SubKind::Open, std::wstring(L"Open Convert..."), std::wstring()});
        CEnumSub* e = new (std::nothrow) CEnumSub(std::move(items));
        if (!e) return E_OUTOFMEMORY;
        HRESULT hr = e->QueryInterface(IID_IEnumExplorerCommand, reinterpret_cast<void**>(ppEnum));
        e->Release();
        return hr;
    }

private:
    ~CConvertMenu() { InterlockedDecrement(&g_objCount); }

    // Adds the file's type and normalized extension to the remembered selection.
    void Remember(int extIndex, const std::wstring& path) {
        m_typeMask |= 1u << kExtTypes[extIndex];
        std::wstring ext = NormalizedExt(path.c_str());
        if (std::find(m_exts.begin(), m_exts.end(), ext) == m_exts.end()) m_exts.push_back(ext);
    }

    unsigned m_typeMask = 0;           // bit per QuickType of the last GetState selection
    std::vector<std::wstring> m_exts;  // distinct normalized extensions of that selection
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
