# 遊戲逆向工程研究筆記：IL2CPP、記憶體分析與 ACTk 防護研究(TaskBarHero)

> Game Reverse Engineering Study Notes: IL2CPP, Memory Analysis, and ACTk Research

本專案整理一套針對 Unity IL2CPP 遊戲的逆向工程研究流程，內容涵蓋靜態分析、動態記憶體觀察、符號還原、資料結構推導，以及 Anti-Cheat Toolkit（ACTk）保護機制的行為分析。

本筆記的重點不是製作修改器，而是把一次完整的二進位安全研究流程沉澱成可複習、可驗證、可延伸的技術文件。研究視角偏向 Purple Team：同時理解攻擊者如何觀察客戶端狀態，也回到防守方角度討論伺服器權威、反調試、完整性驗證與資料可信邊界。

> Disclaimer: 本專案僅供資訊安全研究、逆向工程學習與防禦設計討論使用。請勿將內容用於破壞遊戲公平性、繞過商業服務限制、侵犯第三方權益或任何未經授權的行為。
## 先說結論

>本專案成功繞過 Anti-Cheat Toolkit 保護機制，並實現遊戲金幣資料的篡改驗證。但本研究純粹作為二進位安全與逆向工程用途，因此底下僅會針對底層觀念與框架概念進行技術沉澱，本專案不提供可直接套用到特定商業遊戲的完整 Cheat Table、固定記憶體位址、可重現的繞過腳本或自動化濫用流程。
>下面文字資訊由AI整理順的語句產出。

<img width="461" height="152" alt="image" src="https://github.com/user-attachments/assets/62085a03-c6bb-45dd-b049-4eb51b04ff4b" />


**Anti-Cheat Toolkit 可以拿來幹什麼？**

* 保護記憶體中的變數。
* 保護和擴展 PlayerPrefs 和二進位檔案。
* 生成建置代碼簽章以進行篡改檢查。
* 檢測 Android 上的非 Play Store 安裝。
* 檢測加速器。
* 檢測時間作弊。
* 檢測 3 種常見的外掛防禦壁壘。
* 檢測外部未知託管組件（代碼注入）。
* 擁有 ObscuredPrefs / PlayerPrefs 編輯器。
## Research Scope

本研究聚焦於以下主題：

- Unity IL2CPP 架構下的程式結構觀察
- `GameAssembly.dll` 與 `global-metadata.dat` 的關係
- `dump.cs` 中類別、欄位偏移與函式位址的解讀方式
- Cheat Engine 在動態分析中的角色
- ACTk `ObscuredTypes` 的資料保護思路
- 客戶端資料保護在面對動態分析時的限制
- 從攻防兩側推導更合理的遊戲安全架構



## Background

Unity 專案若使用 IL2CPP 後端，原本的 C# IL 會被轉換成 C++，再編譯為平台原生機器碼。例如 Windows 平台常見的核心檔案會包含：

- `GameAssembly.dll`: 主要邏輯對應的 Native binary
- `[GameName]_Data/Metadata/global-metadata.dat`: 類別、方法、字串與中繼資料

這代表傳統 .NET 工具無法像分析 Mono build 一樣直接取得完整 C# 邏輯。研究者通常需要先透過 metadata 還原結構，再搭配反組譯與動態觀察理解實際執行流程。

## Toolkit

| Tool | Purpose |
| --- | --- |
| Il2CppDumper | 從 IL2CPP binary 與 metadata 還原類別、方法與欄位結構 |
| Cheat Engine | 動態記憶體觀察、斷點追蹤、反組譯與暫存器狀態分析 |
| Ghidra / IDA Free | 靜態反組譯、交叉引用追蹤與控制流程閱讀 |
| Wireshark / Burp Suite | 後續可用於網路層行為觀察與封包邊界分析 |


## Phase 1: Static Analysis with IL2CPP Dump

>工具(https://github.com/Perfare/Il2CppDumper)

靜態分析的第一步是理解 IL2CPP 將原始 C# 專案轉換成 Native binary 後，哪些資訊仍可被還原。

### Key Files

`GameAssembly.dll` 通常包含遊戲主要邏輯的機器碼。它本身不是一般 .NET assembly，因此不能期待 dnSpy 之類工具直接還原出可讀 C#。

`global-metadata.dat` 則保存 IL2CPP runtime 需要的 metadata，例如類別名稱、方法名稱、欄位資訊、字串參考與型別描述。逆向工具會利用這份資料協助還原符號。

### Output: dump.cs

Il2CppDumper 常見輸出之一是 `dump.cs`。這個檔案看起來像 C#，但它不是原始碼，也通常不包含真正的函式實作。

它的價值在於提供：

- Class / Struct 名稱
- Namespace 與繼承關係
- Field offset
- Method name
- Method RVA / VA / Offset
- 部分 generic type 與 nested type 資訊

閱讀 `dump.cs` 時，應把它視為索引與地圖，而不是可編譯的程式碼。真正的邏輯仍需要回到 Native disassembly 或 runtime 行為中確認。
<img width="718" height="372" alt="image" src="https://github.com/user-attachments/assets/bd8860a1-184a-4598-9544-bd8d482c0538" />


### Static Analysis Goals

這個階段的主要目標：

- 找到與研究目標相關的類別，例如 player data、currency、inventory、drop table、battle state
- 建立欄位名稱與記憶體 offset 的對照
- 標記可疑方法，例如 setter、constructor、serializer、validation routine
- 將高階語意與低階位址建立關聯

範例觀察方向：

```text
Class: PlayerResource
Field: coins
Possible meaning: currency-like value
Next step: observe writes during runtime
```

這類筆記能幫助後續動態分析更快縮小範圍。

## Phase 2: Dynamic Memory Analysis

動態分析的核心是觀察程式在執行期間如何讀取、寫入與轉換資料。

Cheat Engine 在這裡扮演的角色不是單純搜尋數值，而是作為 runtime debugger 使用。常見分析任務包含：

- 搜尋候選數值
- 觀察目標地址被哪些指令讀取或寫入
- 檢查暫存器與 call stack
- 對照 `dump.cs` 中的 method offset
- 判斷資料是明文、加密值、快取值還是 UI 顯示值

### Typical Workflow

1. 先透過遊戲內可控行為製造數值變化。
2. 使用合適資料型別縮小候選位址，例如 4-byte integer 或 float。
3. 針對候選地址觀察 access / write instruction。
4. 將觸發的指令位址回推到模組與函式。
5. 比對 `dump.cs`、反組譯工具與 runtime call stack。
6. 判斷該地址代表真實狀態、暫存狀態、顯示狀態或加密後狀態。

這個流程的重點是交叉驗證。單一數值搜尋結果很容易誤判，必須結合結構、指令、呼叫路徑與實際遊戲行為一起看。

## Applied Case Study: Tactical Attack Workflow

前面的章節偏向方法論；本節補上本次實驗室環境中的實際推進路線。這裡不記錄可直接套用到特定遊戲的固定位址、完整注入腳本或具體改值參數，而是保留攻擊鏈的判斷順序、卡關原因、轉向策略與防禦結論。

```text
[Attack Path Overview]

Chain A: protected numeric value analysis
memory scan
  -> access breakpoint
  -> observe packed 16-byte movement
  -> identify decode / validation lifecycle
  -> avoid pre-decode mutation
  -> observe safer post-validation state

Chain B: local data structure analysis
dump.cs symbol review
  -> identify container-returning routine
  -> inspect return-time registers
  -> dereference List<T> / array structure
  -> map object field layout
  -> evaluate client-side authority weakness
```

### Chain A: ACTk Protected Value Analysis

第一條攻擊鏈從「畫面上可觀察的數值」開始，但真正的突破點不是數字本身，而是數字背後的保護流程。

#### Step 1: Trigger Controlled Value Changes

先在遊戲內製造可重複的數值變化，例如資源增加、消耗或結算。這一步的目的不是立刻修改，而是取得穩定的觀察樣本。

研究紀錄應包含：

- 哪個操作會觸發數值變動
- 數值變動前後的範圍
- UI 顯示是否即時更新
- 是否存在延遲同步或重新整理行為

#### Step 2: Scan and Classify Candidate Addresses

使用 Cheat Engine 搜尋候選地址後，不應立刻假設候選值就是真實狀態。實驗中可觀察到，直接修改外顯值可能導致狀態被重設、回復或歸零，這通常代表該值只是快取、顯示值，或與內部校驗資料不一致。

這一步的判斷重點：

- 候選地址是否穩定存在
- 修改後是否被下一次邏輯更新覆蓋
- 是否同時存在多個相似數值
- 是否有 encrypted value、fake value、runtime key 的跡象

#### Step 3: Use Access Breakpoints to Find the Real Flow

對候選地址下 access / write breakpoint，觀察是哪一段指令讀寫它。若看到 16-byte 搬移、XMM 暫存器、stack 暫存區與多個欄位一起出現，通常代表程式正在搬移一整塊受保護狀態，而不是單純處理一個明文數字。

```text
[Observation]
single displayed value
      │
      ▼
multiple memory fields move together
      │
      ▼
protected state is likely involved
```

本次實驗中，真正有價值的發現不是「哪個地址可以改」，而是「哪個位置還沒有完成解密與校驗」。這個差異直接決定後續嘗試會成功、失敗、歸零，還是產生怪異常數。

#### Step 4: Avoid the Pre-Decode Trap

一開始若在資料剛被載入暫存器時就嘗試改動，很容易把明文塞進原本預期為密文的流程。後續 decode、XOR、bit shifting 或 integrity check 會把錯誤格式的資料繼續處理，最後導致不可預期結果。

```text
[Failed Attempt Pattern]
protected block loaded
  -> premature mutation
  -> decode routine treats mutated bytes as protected data
  -> corrupted runtime value or validation failure
```

這個踩坑點很重要，因為它說明動態分析不能只看「資料被讀取」；還要判斷資料在生命週期中的階段。

#### Step 5: Move Observation Toward Post-Validation State

後續策略改為觀察 decode / validation routine 之後的狀態，例如函式返回前、資料準備寫回前、UI 渲染前，或邏輯判斷即將使用 runtime value 的位置。

在授權實驗室環境中，這類觀察點可以用來驗證：

- 保護資料何時轉為 runtime value
- integrity check 是否已經完成
- UI 使用的是哪一份資料
- gameplay logic 使用的是哪一份資料
- 客戶端是否對該狀態擁有過高權威

### Chain B: Local Rate / Drop Table Structure Analysis

第二條攻擊鏈不是從單一數值切入，而是轉向資料結構。當某些結果看似不是簡單數字，而是由本地資料表、掉落池、清單或權重模型組成時，分析重點會從「搜尋值」變成「理解容器」。

#### Step 1: Search Symbols in dump.cs

先在 `dump.cs` 中尋找和資料表、掉落、清單、獎勵、權重或設定檔相關的類別與方法。目標不是只找某個欄位，而是建立一條從高階語意到低階位址的路徑。

研究紀錄可以包含：

```text
Candidate class:
Candidate method:
Return type:
Related field:
RVA / Offset:
Reason for interest:
```

如果某個方法回傳 `List<T>`、array 或自訂資料集合，就代表後續可能需要分析 IL2CPP 中的容器布局。

#### Step 2: Break Near Function Return

針對疑似會回傳資料集合的方法，觀察函式返回前後的暫存器狀態。這個時間點通常可以看到：

- 回傳物件指標
- 呼叫者即將使用的資料集合
- 容器內部 array 或 items 指標
- 元素物件地址

```text
[Return-Time Observation]
target routine
  -> builds or fetches data list
  -> prepares return object
  -> caller consumes list
```

這種觀察方式比直接掃描權重數字更穩，因為它能把「資料從哪裡來」與「誰會使用它」串起來。

#### Step 3: Dereference List<T> and Array Layers

IL2CPP 中的 `List<T>` 通常不是直接等於第一個元素。它會有容器物件、內部 array、array header、元素儲存區或元素指標等多層結構。

概念路徑如下：

```text
List<T>
  -> internal items / array reference
  -> array header
  -> element storage
  -> object instance
  -> target field
```

本次實驗的關鍵收穫是：看到暫存器裡有一個地址，不代表那就是目標欄位。必須逐層確認它是容器、array、元素，還是元素內部欄位。

#### Step 4: Map Field Offsets Back to dump.cs

當找到元素物件後，再回到 `dump.cs` 比對欄位順序、型別與 field offset。這一步可以避免把相鄰欄位誤判成目標欄位，也能驗證目前解引用鏈是否合理。

建議驗證問題：

- 目前地址是否落在合理的物件範圍內？
- 欄位型別是否符合預期？
- 相鄰欄位是否也符合 `dump.cs` 的結構？
- 修改測試是否只影響預期行為？
- 結果是否會被伺服器覆蓋或拒絕？

#### Step 5: Derive the Security Finding

若本地資料表或權重模型能影響結果，這代表該結果至少部分依賴客戶端狀態。從防守角度，這不是「哪個 offset 被找到」的問題，而是權威邊界設計問題。

```text
[Security Finding]
client-side configurable model
  -> local data structure can be observed
  -> local fields can influence runtime behavior
  -> high-value outcomes should be server-authoritative
```

### Lessons from the Tactical Flow

這次實驗最重要的不是單一技巧，而是推進順序：

- 先用可重複行為建立觀察樣本
- 再用 breakpoint 找到真實讀寫路徑
- 遇到保護型資料時，先理解生命週期再判斷注入點
- 遇到容器型資料時，先解引用結構再討論欄位
- 最後把客戶端可控結果轉換成防禦架構上的發現

這也解釋了後面幾節為什麼會強調 `ObscuredTypes`、Hook 觀察點、`List<T>` 解引用與 server-authoritative design。理論不是事後裝飾，而是從實戰卡關中萃取出來的規則。

## Phase 3: Understanding ACTk ObscuredTypes

Anti-Cheat Toolkit（ACTk）是 Unity 生態中常見的客戶端防改套件。其 `ObscuredTypes` 系列型別會避免敏感數值以直觀明文形式長時間存在記憶體中。

以 `ObscuredFloat` 這類型別為例，實際資料結構可能包含：

- encrypted value
- crypto key
- fake value / honeypot value
- hash 或完整性檢查資料
- initialized flag

因此，直接搜尋並修改畫面上看到的數字，可能只是在改 UI 快取或中間值。若內部密文、key、hash 或校驗流程不一致，程式就可能判定資料被篡改，進而重設數值、拒絕狀態或觸發其他保護邏輯。

### Conceptual Memory Layout

不同 ACTk 版本、編譯設定與遊戲實作可能導致結構細節不同，因此下面不是固定 offset 表，而是用來理解 `ObscuredTypes` 的概念模型。

```text
[Obscured Numeric Value: Conceptual Layout]
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│ control / flags  │ runtime key       │ encrypted payload│ validation data  │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
          │                  │                  │
          │                  │                  └── encrypted or transformed value
          │                  └── dynamic key used during encode / decode
          └── initialization state, fake value marker, or integrity metadata
```

在動態分析時，容易看到 16-byte 搬移、XMM 暫存器、stack 暫存區與結構欄位一起出現。這類現象通常代表程式不是單純讀寫一個 `float` 或 `int`，而是在搬移一整塊受保護的資料狀態。

### Why Plain Memory Editing Fails

傳統記憶體修改常假設：

```text
displayed value == real value in memory
```

但在 ACTk 類型中，更接近：

```text
displayed value = decrypt(encrypted value, key)
valid state = integrity_check(encrypted value, key, hash, fake value)
```

這代表研究重點應從「找到數字」轉向「理解資料生命週期」：

- 數值何時被建立？
- 何時被加密？
- 何時被解密？
- 哪裡進行一致性檢查？
- 哪些欄位只是顯示或快取？
- 哪些函式才是狀態變更的權威入口？

### Practical Pitfall: Editing Before Decode

實戰中很常見的一個誤判，是在資料剛被載入暫存器時就急著下結論。例如看到類似「一次搬移 16 bytes 到 XMM 暫存器」的指令時，直覺會以為該暫存器中已經是可用的明文數值。

但對 `ObscuredTypes` 來說，這一刻拿到的很可能仍是密文資料塊、key、flag 或校驗資料的組合。若在解密或驗證流程完成前改動它，後續演算法會把錯誤資料繼續當作合法狀態處理，最後可能產生幾種現象：

- 顯示值變成固定怪異常數
- 數值短暫改變後立刻回復
- 安全校驗將資料歸零
- 遊戲邏輯拒絕該狀態
- 程式進入例外或崩潰

```text
[Wrong Mental Model]
load value -> edit plaintext -> use value

[More Accurate Model]
load protected block -> decode / validate -> derive runtime value -> use value
```

這也是為什麼單純搜尋畫面數字通常不可靠。真正值得觀察的是資料從「受保護狀態」轉換成「可運算狀態」的生命週期。

## Phase 4: Code Flow and Hooking Concepts

在二進位安全研究中，Inline Hook 是一種觀察或改變程式控制流程的技術。它的概念是在特定指令位置轉移執行流程，執行研究者自定義的邏輯後，再回到原本流程。

本專案只討論其研究意義與防禦啟示，不收錄可直接套用於特定目標的完整注入腳本。

### Conceptual Model

```text
original function
    -> prepare data
    -> validate or transform data
    -> write result
    -> return

instrumented flow
    -> prepare data
    -> validate or transform data
    -> observe selected registers / memory
    -> optionally test controlled behavior in a lab environment
    -> return to original flow
```

從研究角度來看，Hook 的價值在於理解程式於「資料即將寫入」或「函式即將返回」時的真實狀態。這可以協助判斷：

- 哪些資料是加密前的明文
- 哪些資料是加密後的密文
- key 與 value 是否同時存在於暫存器或 stack
- 防改檢查是在寫入前、寫入後，還是下一次讀取時發生

### Better Observation Points

若目標是研究資料生命週期，注入點的選擇比修改內容本身更重要。常見觀察點包括：

- getter / setter 入口
- decode / encode routine 前後
- integrity check 前後
- 函式返回前
- UI render 或 network serialization 之前

```text
[Protected Value Lifecycle]
encrypted state
      │
      ▼
decode / validate
      │
      ▼
runtime value
      │
      ├── gameplay calculation
      ├── UI rendering
      └── network serialization
```

在實驗室環境中，研究者通常會先觀察每個節點的暫存器、stack 與物件欄位狀態，再判斷哪一段才是安全機制真正生效的位置。這種方式比直接在第一個可疑指令修改資料更穩定，也比較能得到可解釋的結論。

### C# Container Dereferencing

IL2CPP 會把 C# 高階容器轉換成 Native runtime 中可操作的物件結構。當分析 `List<T>`、array 或自訂資料表時，常會需要理解多層指標解引用。

以下是概念模型，不代表所有版本與所有遊戲都使用相同 offset：

```text
[List<T> Conceptual Dereference Chain]
List<T> object
      │
      └── internal array / items pointer
              │
              └── array header
                      │
                      └── element pointer or inline element storage
                              │
                              └── target object fields
```

這種分析方式可用來回答幾個問題：

- 函式回傳的是容器本身，還是容器中的元素？
- 目前暫存器保存的是物件地址、array 地址，還是欄位值？
- 目標欄位是 value type inline storage，還是 reference type object？
- 欄位 offset 是否與 `dump.cs` 的結構描述一致？

容器解引用的研究價值在於理解資料結構，而不是盲目追逐某個固定地址。固定 offset 很容易因版本、平台、編譯器與資料模型變動而失效。

### Defensive Takeaway

ACTk 這類工具能提高客戶端修改成本，但不能讓客戶端變成可信環境。只要重要資料在本機完成計算或判定，攻擊者就有機會透過動態分析觀察資料流。

因此，安全設計應避免把關鍵結果完全交給客戶端決定。

## Purple Team Findings(AI提供建議)

本次研究可以整理出幾個攻防共同重點。

### 1. Client-side memory is observable

不論資料是否經過 XOR、hash、fake value 或 runtime key 保護，只要資料需要在客戶端被使用，就會在某個時間點被載入暫存器、stack 或 heap。

防守方不能假設「加密後存在記憶體」就等於安全，只能視為提高分析門檻。

### 2. Server-authoritative design is critical

貨幣、掉落、抽卡、排行榜、交易、經驗值、付費道具等高價值資料，應由伺服器決定最終結果。

比較安全的設計：

```text
client sends intent
server validates rules
server computes result
server returns signed state
client displays result
```

風險較高的設計：

```text
client computes result
client stores result
server accepts client state
```

### 3. Anti-cheat should be layered

單一保護機制容易被繞過或觀察。較合理的做法是多層搭配：

- Server-side validation
- Rate limiting
- Replay protection
- Session token and request signing
- Runtime integrity checks
- Anti-debugging
- Obfuscation
- Telemetry-based anomaly detection
- Economy and gameplay sanity checks

重點不是讓每一層都完美，而是讓攻擊成本、偵測能力與修復速度形成整體防線。

### 4. Logs and telemetry matter

若系統只在客戶端阻擋，而伺服器沒有足夠 telemetry，防守方會很難理解攻擊模式。

建議觀察：

- 不合理的資源增長速度
- 掉落結果與機率模型偏差
- 異常關卡完成時間
- 高頻率重試或失敗請求
- 同裝置、多帳號、異常 session pattern
- 客戶端版本、完整性檢查結果與行為數據之間的關聯



## Summary

這份研究筆記展示了 Unity IL2CPP 遊戲在二進位層面的分析方式：先透過 metadata 還原高階結構，再使用動態工具觀察 runtime 行為，最後從 ACTk 類型的保護模型推導客戶端安全的邊界。

最重要的結論是：客戶端保護能提高攻擊成本，但不能取代伺服器權威。真正穩健的遊戲安全設計，需要把關鍵資產、機率結果與狀態結算放在可信後端，並以多層防禦與 telemetry 持續驗證整體風險。
