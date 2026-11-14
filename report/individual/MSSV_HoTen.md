# Báo cáo cá nhân — Day 6: Data Ingestion Engineering

**Họ và tên:** Nguyễn Thị Huấn Giang  
**MSSV:** 2A202603538

## 1. Dữ liệu và pipeline

### 1.1. Chủ đề và nguồn dữ liệu

- **Chủ đề:** Functions and Graphs — nội dung về hàm số và đồ thị.
- **Nguồn:** OpenStax, *Calculus Volume 1*.
- **Giấy phép:** CC BY-NC-SA 4.0.
- **Phạm vi:** 30 trang PDF vật lý, từ trang 16 đến trang 45.
- **Quy tắc đánh số trang:** Sử dụng số trang vật lý trong PDF làm page ID để truy xuất và đối chiếu evidence.
- **Phân chia section:**
  - Section 1.1 — Review of Functions: trang 16–37.
  - Section 1.2 — Basic Classes of Functions: trang 38–45.
- **Tổng số ký tự sau chuẩn hóa:** 45.968 ký tự.

### 1.2. Chuẩn hóa và giới hạn dữ liệu

Pipeline sử dụng PyPDF để trích xuất nội dung PDF. Văn bản sau đó được chuẩn hóa Unicode bằng NFKC, chuẩn hóa khoảng trắng và xuống dòng, đồng thời giữ lại ranh giới trang để đảm bảo khả năng truy xuất nguồn.

Một số giới hạn được ghi nhận:

- Công thức toán học và ký hiệu trong PDF không được trích xuất đầy đủ.
- Một số đoạn văn bị mất biểu thức hoặc ký hiệu, khiến nội dung không còn đầy đủ về mặt toán học.
- Một số chunk chứa footer, số trang hoặc nội dung ít thông tin.
- Việc chia chunk có thể làm nội dung liên quan bị tách thành nhiều đoạn.

Những vấn đề này ảnh hưởng trực tiếp đến chất lượng embedding và retrieval.

### 1.3. Embedding và vector store

- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`.
- **Provider:** Sentence Transformers, chạy local.
- **Số chiều:** 384.
- **Vector store:** PostgreSQL kết hợp pgvector.
- **Similarity metric:** Cosine distance.
- **Top-K:** 3.
- **Lệnh chạy:**

```bash
python -m src.run
```

Pipeline thực hiện trích xuất PDF, chuẩn hóa văn bản, tạo chunk, embedding, lưu vector và truy xuất theo benchmark.

Do sử dụng model local nên không phát sinh chi phí gọi API embedding. Chi phí tài nguyên máy và điện năng chưa được đo. Phiên bản cụ thể của PostgreSQL và pgvector chưa được ghi nhận.

### 1.4. Metadata

Các trường metadata chính:

| Trường | Ý nghĩa |
|---|---|
| `document_id` | Định danh tài liệu |
| `source` | Nguồn tài liệu |
| `page` | Trang PDF vật lý |
| `section` | Phân loại section |
| `has_text` | Trang có văn bản hay không |
| `page_type` | Loại trang |
| `character_count` | Số ký tự trích xuất |

Trường lọc bổ sung là `section`, có hai giá trị `1.1` và `1.2`. Giá trị được xác định dựa trên vị trí trang trong tài liệu.

Lý do lựa chọn là section phản ánh cấu trúc nội dung, giúp giới hạn phạm vi tìm kiếm theo chủ đề và hỗ trợ đánh giá tác động của metadata filtering.

---

## 2. Cấu hình và benchmark

### 2.1. Cấu hình A/B/C

| Strategy | Chunking | Kích thước | Overlap | Metadata filter |
|---|---|---:|---:|---|
| A | Fixed-size | 500 ký tự | 50 | Không |
| B | Paragraph-based | Tối đa 500 ký tự | 0 | Không |
| C | Paragraph-based | Tối đa 500 ký tự | 0 | Có, theo `section` |

Cả ba chiến lược sử dụng cùng corpus, embedding model, vector store, cosine distance và Top-3.

- A–B dùng để đánh giá ảnh hưởng của phương pháp chunking.
- B–C dùng để đánh giá ảnh hưởng của metadata filtering.
- B và C giữ nguyên phương pháp chunking; khác biệt duy nhất là metadata filter.

### 2.2. Benchmark

Benchmark gồm 20 câu hỏi bằng tiếng Việt:

- 15 câu Development.
- 5 câu Test.
- 4 câu có metadata filter.
- Có câu hỏi trực tiếp, diễn đạt lại và câu hỏi cần truy xuất nội dung theo ngữ cảnh.

Mỗi câu hỏi có expected answer, gold source, gold page và evidence quote.

Evidence được kiểm tra bằng cách đối chiếu nội dung chunk với nguồn và trang chuẩn. Evidence Hit@3 yêu cầu kết quả Top-3 có đúng nguồn, đúng trang và chứa evidence quote đã xác định.

Tiêu chí lựa chọn chiến lược tập trung vào khả năng truy xuất đúng nguồn, đúng trang, đủ evidence và khả năng sử dụng metadata. Không sử dụng test set để điều chỉnh tham số trong quá trình thực nghiệm.

---

## 3. Kết quả

### 3.1. Retrieval metrics

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian embedding + storage | Chi phí |
|---|---|---:|---:|---:|---:|---|
| A | Dev | 1/15 | 1/15 | 119 | 7,69 giây | Chưa đo |
| A | Test | 0/5 | 0/5 | 119 | 7,69 giây | Chưa đo |
| B | Dev | 0/15 | 0/15 | 106 | 7,75 giây | Chưa đo |
| B | Test | 0/5 | 0/5 | 106 | 7,75 giây | Chưa đo |
| C | Dev | 0/15 | 0/15 | 106 | 6,28 giây | Chưa đo |
| C | Test | 0/5 | 0/5 | 106 | 6,28 giây | Chưa đo |

Thời gian là thời gian embedding và lưu trữ được ghi nhận trong lần chạy pipeline, không phải tổng thời gian của toàn bộ quá trình chuẩn bị dữ liệu.

### 3.2. Đánh giá thủ công

| Strategy | Coherence trung bình /2 | Metadata đủ và đúng | Filter tuân thủ | Grounding |
|---|---|---|---|---|
| A | Chưa chấm (10 mẫu) | Chưa tổng hợp | N/A với câu không lọc | Chưa chấm |
| B | Chưa chấm (10 mẫu) | Chưa tổng hợp | N/A với câu không lọc | Chưa chấm |
| C | Chưa chấm (10 mẫu) | Chưa tổng hợp | Chưa tổng hợp | Chưa chấm |

Các file đánh giá đã được tạo nhưng chưa hoàn thành việc chấm điểm:

- `manual_coherence.csv`: 30 mẫu, 10 mẫu mỗi chiến lược.
- `manual_grounding.csv`: 15 mẫu, 5 câu mỗi chiến lược.
- `metadata_review.csv`: 45 dòng, tương ứng Top-3 của 5 câu test cho mỗi chiến lược.

Do chưa có điểm và nhận xét của người đánh giá, báo cáo không tự tính trung bình hoặc tỷ lệ đánh giá thủ công.

### 3.3. Trace và output

Các kết quả được lưu tại `starter/outputs/`:

- `retrieval_metrics.json`: kết quả retrieval metrics.
- `retrieval_traces.json`: Top-3 chunks, similarity score và metadata.
- `ingestion_report.json`: báo cáo ingestion.
- `manual_coherence.csv`: dữ liệu đánh giá coherence.
- `manual_grounding.csv`: dữ liệu đánh giá grounding.
- `metadata_review.csv`: dữ liệu kiểm tra metadata và filter compliance.

---

## 4. Phân tích và kết luận

### 4.1. So sánh A–B

A tạo 119 chunks, B tạo 106 chunks.

Fixed-size chunking giúp kích thước chunk đồng đều nhưng có thể cắt ngang ranh giới ngữ nghĩa. Paragraph-based chunking có khả năng giữ cấu trúc đoạn văn tốt hơn nhưng không đảm bảo retrieval tốt hơn.

Trong thực nghiệm, A đạt 1/15 Hit@1 và 1/15 Evidence Hit@3 trên Dev, trong khi B đạt 0 ở cả hai chỉ số.

Điều này cho thấy chất lượng chunking không phải yếu tố duy nhất quyết định retrieval. Chất lượng văn bản sau extraction và sự tương thích ngôn ngữ cũng có ảnh hưởng đáng kể.

### 4.2. So sánh B–C

B và C có cùng số lượng chunks là 106, cùng phương pháp chunking và embedding model. C bổ sung metadata filtering theo section.

Kết quả hiện tại chưa chứng minh được metadata filtering cải thiện retrieval theo Hit@1 và Evidence Hit@3.

Metadata filtering có thể thu hẹp phạm vi tìm kiếm, nhưng nếu thông tin section không phù hợp hoặc câu hỏi không cung cấp đủ ngữ cảnh để chọn section chính xác, filter có thể loại bỏ chunk chứa evidence cần thiết.

### 4.3. Ví dụ lỗi truy xuất

**Q01 — Định nghĩa hàm số**

- Nguồn chuẩn: OpenStax Calculus Volume 1, trang 17.
- Nội dung cần tìm: Một hàm số ánh xạ mỗi phần tử trong miền xác định tới đúng một phần tử trong miền giá trị.
- Kết quả: Top-3 không đưa được chunk đúng trang và chứa evidence cần thiết lên vị trí phù hợp.

Nguyên nhân có thể liên quan đến việc câu hỏi bằng tiếng Việt trong khi corpus và embedding model sử dụng tiếng Anh.

**Q16 — Đường thẳng đứng và đồ thị hàm số**

- Nguồn chuẩn: OpenStax Calculus Volume 1, trang 40.
- Nội dung cần tìm: Đường thẳng đứng có thể cắt đồ thị tại nhiều hơn một điểm với cùng một giá trị x, vi phạm điều kiện của hàm số.
- Kết quả: Top-3 của A trả về các chunk ở trang 27, 21 và 22, không chứa evidence đúng trang 40.

Đây là trường hợp truy xuất được nội dung cùng tài liệu nhưng không đúng vị trí và không đủ bằng chứng cho câu hỏi.

### 4.4. Chiến lược và đánh đổi

Chưa có đủ bằng chứng để kết luận chiến lược nào vượt trội tổng thể.

A có kết quả khác 0 trên Dev và có số lượng chunk lớn hơn. B giữ cấu trúc đoạn văn nhưng chưa cho thấy cải thiện retrieval. C có khả năng thu hẹp phạm vi truy xuất bằng metadata nhưng chưa chứng minh được hiệu quả qua kết quả hiện tại.

Nếu chọn một baseline để tiếp tục phát triển, có thể giữ A do đã có kết quả retrieval khác 0 trên Dev. Đây không phải kết luận A tốt hơn về tổng thể; cần đánh giá thủ công và kiểm tra thêm trên benchmark.

### 4.5. Hạn chế và hướng cải tiến

Các hạn chế chính:

1. PDF extraction làm mất một số công thức và ký hiệu toán học.
2. Corpus tiếng Anh trong khi benchmark sử dụng câu hỏi tiếng Việt.
3. Một số chunk chứa footer hoặc nội dung ít thông tin.
4. Evidence matching dựa trên so khớp chuỗi chính xác, chưa đánh giá đầy đủ các trường hợp tương đương ngữ nghĩa hoặc evidence nằm ở nhiều chunk.
5. Ba bảng đánh giá thủ công chưa được chấm điểm.
6. Test set chỉ có 5 câu nên khả năng khái quát còn hạn chế.
7. Thời gian và chi phí tài nguyên chưa được đo đầy đủ.

Hướng cải tiến:

- Sử dụng công cụ trích xuất PDF có khả năng bảo toàn công thức toán học tốt hơn.
- Loại bỏ footer, header và chunk ít thông tin.
- Thử nghiệm embedding model đa ngôn ngữ.
- Bổ sung reranking để cải thiện thứ tự Top-K.
- Chọn cùng vị trí nội dung khi đánh giá coherence giữa các chiến lược.
- Hoàn thành đánh giá thủ công và mở rộng test set.

### 4.6. Kết luận

Thực nghiệm đã xây dựng và chạy được pipeline ingestion từ PDF đến PostgreSQL/pgvector, sử dụng embedding model thực tế và triển khai ba chiến lược A/B/C.

Kết quả retrieval hiện còn thấp. Thí nghiệm cho thấy thay đổi phương pháp chunking hoặc bổ sung metadata filtering không mặc nhiên cải thiện chất lượng truy xuất.

Chất lượng RAG phụ thuộc đồng thời vào dữ liệu đầu vào, khả năng trích xuất nội dung, phương pháp chia chunk, embedding model, metadata và cách đánh giá. Cần hoàn thiện đánh giá thủ công và cải thiện chất lượng dữ liệu trước khi có thể đưa ra kết luận chắc chắn về chiến lược tối ưu.
