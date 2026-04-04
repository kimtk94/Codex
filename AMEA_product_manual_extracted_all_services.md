# AMEA Product Manual 원문 발췌 (All Services)

- Source: `AMEA Product Manual.docx`
- Scope: 문서 전체 서비스(메타볼로믹스, 프로테오믹스, 싱글셀, 공간전사체 등) 원문 텍스트 발췌
- Method: DOCX XML 텍스트 추출 후 즉시 중복 줄만 제거하여 Markdown으로 구성

Novogene Product Manual
Metabolomics Service
AMEA 2026.02
(This product manual is strictly confidential and intended solely for internal use within the AMEA region. The contents must not be shared with any external parties without prior written approval from the APM Director. For any product-related inquiries, please contact the APM Team.)
Product Manual Revisions
Subject
Novogene Product Manual- Metabolomics Service- 2026 V1.0
Revision Number
2026 V1.0
Issue Date
Feb, 2026
Prepared by
Geng Jiaxin
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2026 V1.0
Pg 6- Untargeted metabolomics instrument update to Orbitrap ExplorisTM 120 Pg 6- From April 15, 2026, SG Lab can extract all sample types for untargeted and quasi-targeted metabolomics.
Pg 15- The untargeted metabolomics standard compound database has been expanded from 15,000 to 18,000 standards.
Pg 23, 24- FAQ content has been updated.
Geng Jiaxin
2026.2.4
Contents
Metabolomics Service Overview6
Basic Concepts in Metabolomics7
- What is Metabolism?7
- What is Metabolite?7
- What is Metabolomics?8
Study Approaches in Metabolomics9
## Introduction to Untargeted Metabolomics10
- What is Untargeted Metabolomics10
## Workflow of Untargeted Metabolomics10
## Sample Requirements and Guidelines11
Data Acquisition in Untargeted Metabolomics Plus and Pro12
Acquisition Parameters12
Data Acquisition Process13
Data Preprocessing and Analysis14
BI analysis16
Summary of Untargeted Metabolomics Plus and Pro17
Experience of Number of Total detection and Level1 detection18
Key Advantages of Untargeted Metabolomics Plus and Pro19
Recommended Strategies for Untargeted Metabolomics20
Customer Literature and Application Scenarios21
## FAQ22
## Introduction to Quasi-targeted Metabolomics25
- What is Quasi-targeted Metabolomics25
Project workflow of Quasi-targeted Metabolomics25
Sample Collection and Requirements26
Data Acquisition26
Acquisition Parameters26
Process of LC-MS detection27
Data Preprocessing and Analysis27
In-house Quasi-targeted Metabolomics Database27
Number of Level1 Detection30
BI analysis31
## FAQ32
## Introduction to Targeted Metabolomics34
- What is Targeted Metabolomics34
## Workflow of Targeted Metabolomics34
Targeted Metabolomics Products35
BI Analysis36
Comparing Metabolomics Services and Choosing the Right Option38
Multi-omics Analysis40
Parallel Research Framework of Multi-omics Research40
Significance of Multi-omics Integration40
Demo Results for Metabolomics- transcriptomics and Metabolomics- microbiomics Integration Analysis41
Appendix42
Bioinformatic Analysis Form for Metabolomic Project42
Note42
Selected Publications Mentioning Novogene42
## Metabolomics Service Overview
Service Type
Column
Minimum Sample requirement and replicates
Equipment used
Default data format
Turnaround time
** Sample pretreatment
Untargeted Metabolomics Plus
C18
20 working days
(<100 samples)
Extraction in SG (From April 15,2026 onward, all sample types can be processed
for extraction.)
Untargeted Metabolomics Pro
C18 and HILIC
Minimum 6 samples per project per batch.
≥ 6 replicates are
highly recommended
Orbitrap ExplorisTM 120
.mzxML format*
25 working days
(<100 samples)
Extraction in SG (From April 15,2026 onward, all sample types can be processed
for extraction.)
Lipidomics
30 working days
(<100 samples)
Extraction in TJ
Quasi Untargeted Metabolomics
SCIEX QTRAP 6500+
/
32 working days
(<30 samples)
Extraction in SG (From April 15,2026 onward, all sample types
can be processed for extraction.
Targeted Metabolomics
Minimum 8 samples per panel.
SCIEX QTRAP 6500+;
Thermo TSQ Altis (SCFA)
35 working days
(<30 samples)
Extraction in TJ
- Note:
* Our default data release for untargeted metabolomics Plus/ Pro services is .mzxML file. Special application and approval workflow is required if KOL customer requests raw data for metabolomics services.
** Sample Pretreatment:
Sample Pretreatment
Sample Type
Available Products
Extraction in SG
Human and animal tissue, plant samples, Plasma / serum, Feces and intestinal content, Saliva, Urine
Refer to above form
Extraction in TJ
(Targeted metabolomics)
Human and animal tissue, plant samples, Plasma / serum, Feces and intestinal content, Saliva, Urine, Tears, Microbe samples, Cell samples
The sample types that SG lab cannot do pretreatment, with products in above form.
Basic Concepts in Metabolomics
- What is Metabolism?
Metabolism refers to the network of biochemical reactions that sustain life in every organism. The core functions are to:
Generate energy by converting nutrients or stored fuel into usable ATP to power cellular activities.
Provide building blocks for the synthesis of macromolecules—proteins, lipids, nucleic acids and carbohydrates.
Remove waste products created during these reactions to maintain cellular health.
Because these reactions are driven by specific enzymes, they enable cells and organisms to grow, reproduce, preserve structural integrity and adapt to their environment.
- What is Metabolite?
Metabolites are the end products of metabolism, which are small molecules less than 1500 Da in molecular weight (typically 100-1000Da). Metabolites
have a wide range of functions, including cell growth support, defence and inhibition, and stimulation. They include amino acids, alcohols, vitamins, organic acids, and many other types of molecules, and they are often the building blocks for larger compounds. Identifying metabolites and how they interact with one another - and how those interactions change under certain conditions - can aid in the discovery and understanding of how organisms work, why diseases develop (or not), why treatments are successful or not, and so on.
- What is Metabolomics?
Metabolomics, an emerging omics technology following genomics, transcriptomics, and proteomics, constitutes a crucial component of systems biology. It aims to investigate changes in metabolites within biological systems (cells, tissues, etc.) following stimulation or perturbation, or their temporal variation patterns. By identifying differential metabolites between experimental and control groups, metabolomics explores the biological processes involving these metabolites, thereby elucidating their roles in life activity mechanisms. As the omics discipline closest to phenotypic expression, metabolomics serves as an extension of transcriptomics and proteomics, providing a more direct and precise reflection of an organism's physiological state.
Figure 1 Metabolomics, an emerging omics technology that follows genomics, transcriptomics, and proteomics
As the omics discipline closest to phenotypic expression, metabolomics serves as an extension of transcriptomics and proteomics, providing a more direct and precise reflection of an organism's physiological state.
Study Approaches in Metabolomics
Metabolomics can be studied through two main approaches: untargeted and targeted metabolomics.
The untargeted approach aims to simultaneously detect hundreds to thousands of small molecules in a biological sample, providing broad and comprehensive metabolite coverage. It is typically used for initial large-scale screening to discover potential biomarkers or metabolic changes.
In contrast, the targeted approach focuses on a predefined set of metabolites, enabling precise and in-depth quantitative validation of findings identified in the untargeted stage, though with narrower metabolite coverage.
## Introduction to Untargeted Metabolomics
- What is Untargeted Metabolomics
Untargeted metabolomics offers a comprehensive and unbiased overview of an organism’s metabolic state, enabling the detection of a wide range of metabolites. This approach supports the discovery of novel biomarkers, metabolic pathways, and disease-related mechanisms that may otherwise remain undetected.
Recent advances in high-throughput technologies, particularly mass spectrometry and chromatography - have made untargeted metabolomics more powerful, accessible, and cost-effective. Improved instrumentation and analytical tools now allow for faster and more precise profiling of complex metabolic systems. Moreover, its integration with genomics, transcriptomics, and proteomics in multi-omics studies provides a more holistic view of biological processes and their roles in health and disease.
## Workflow of Untargeted Metabolomics
The workflow of untargeted metabolomics includes sample collection, metabolite extraction, data acquisition, and data processing. Because metabolites are highly dynamic, chemically diverse, and vary widely in concentration, each step - from sample collection and preservation to extraction and detection
- can affect data quality and ultimately influence bioinformatics outcomes. To ensure accuracy and reliability, Novogene implements rigorous quality control across the entire workflow and adheres to standardized metabolomics protocols, delivering consistent, high-quality results. Novogene currently offers two untargeted metabolomics services: Untargeted Metabolomics Plus and Untargeted Metabolomics Pro.
Figure 2 Project workflow for Untargeted Metabolomics
## Sample Requirements and Guidelines
The SG lab can accept the below sample types for Untargeted Metabolomics service.
Sample type
Untargeted Metabolomics Plus and Pro
Human & Animal tissue
200 mg
Plasma/Serum
200 μL
Feces/Intestinal contents
200 mg
Saliva
200 μL
Urine
200 μL
For more details about sample requirements and preparation method, please click the link: Novogene-AMEA-Sample-Submission-Guideline_Mass-Spectrometry-2025-03-V1.pdf
From April 15,2026 onward, all sample types can be processed for extraction.
*Note:
Common questions during the sample collection stage:
Recommended replicates samples number: At least 30 clinical samples per group, 10 animal model samples per group, and 6 plant samples per group.
Multi-omics studies: When multiple omics platforms are used, prioritize those requiring sample quality control (e.g., RNA sequencing).
Sample storage: Long-term storage at −80 °C after flash-freezing in liquid nitrogen does not affect metabolite detection accuracy.
Below sample types need to do pretreatment in China lab:
Cell samples: Clients should provide cell count results. For untargeted metabolomics, consistent extraction volumes are essential, as this ensures data comparability in the absence of internal quality control. Please ensure the cell count can meet the requirement.
This sample type can be extracted in the Singapore lab but requires special handling during submission.
Swab and skin tape samples: A blank sample should be prepared as a negative control.
Data Acquisition in Untargeted Metabolomics Plus and Pro
Acquisition Parameters
Service
Untargeted Metabolomics Plus
Untargeted Metabolomics Pro
Scan mode
DDA (data dependent acquisition)
After primary ion scanning, the top N precursor ions are sequentially selected for secondary MS/MS fragmentation in the collision cell, with subsequent scanning of product ion m/z and signal intensities
Ion mode
Positive+Negative
Run time
12min
Column
C18
C18+HILIC
MS platform
Orbitrap ExplorisTM 120 mass spectrometer platform
Data Acquisition Process
Figure 3 Process of LC-MS detection and QC preparation method
QC samples are prepared by pooling equal volumes from all experimental samples. The first three QCs are used to equilibrate chromatographic and mass spectrometry systems, while subsequent QCs inserted between experimental samples monitor instrument stability and data quality. Individual QC reports are not provided; instead, the correlation diagram of QC samples is included in the final report.
*Note: Do not add internal standards to experimental samples. For special requests, please contact APM team.
## Data Preprocessing and Analysis
Process of database searching:
We use XCMS software for database searching, as illustrated below.
Figure 4 Workflow of XCMS database search
In-house Untargeted Metabolomics Database and Confidence Level of Metabolites:
Novogene’s in-house untargeted metabolomics database (NovoMetDB-UM) consists of two components: (1) a reference standard database built from MS/MS spectra of over 18,000 commercially purchased authentic standards, and (2) a curated high-quality MS/MS spectral library filtered from public
databases (HMDB, RefMetaDB, and ReSpect for Phytochemicals) after removing low-quality spectra. These components are integrated into a comprehensive spectral library for untargeted metabolomics analysis. The database has been upgraded to version 3.1, now containing more than 18,000 standards in the reference database and over 170,000 compounds in the secondary MS/MS spectral library.
Confidence Level of metabolites: To standardize confidence in metabolite annotation, the Metabolomics Standards Initiative (MSI) introduced four identification levels in 2007, later expanded to five. Each level reflects a different degree of annotation confidence. Level 1 – Confirmed Structure: Compounds are confirmed under the same analytical conditions as the reference standard, including matching retention time (RT), primary mass spectrometry (MS1), and secondary mass spectrometry (MS/MS). Level 1 represents the highest identification accuracy.
Figure 5 Metabolomics Standards Initiative (MSI) proposed by the Chemical Analysis Working Group (CAWG)
## BI analysis
Figure 6 Process of BI analysis of Untargeted Metabolomics
Analysis Content
Standard Analysis
Software
Qualitative and quantitative analysis of metabolites
XCMS
Data quality control
metaX
Metabolite classification and pathway annotation
KEGG,HMDB,LIPIDMaps database
Differential metabolites screening*
metaX
Differential metabolite analysis
R language
KEGG enrichment analysis
R language, KEGG database
GSEA analysis
GSEA program
ROC curve analysis of differential metabolites
R language
- Note: *If biological replicates are less than 3, PCA and PLS-DA analysis will not be performed.
For more details, please check with demo report: https://drive.weixin.qq.com/s?k=AJgAAQcaAAwzPMCcbg
Summary of Untargeted Metabolomics Plus and Pro
Service
Untargeted Metabolomics Plus
Untargeted Metabolomics Pro
Column
C18
C18+HILIC
Database
18,000+ reference stands,170,000+substrances
Number of Level1 identification
Average 900+
Average 1200+
Number of total identification
Average 4000+
Average 5000+
Recommend strategies
A large number of identifications, high cost effective and short cycle time
The highest number of identifications, the greatest accuracy, and suitable for well-funded customers with high quality requirements.
Experience of Number of Total detection and Level1 detection
Untargeted Metabolomics Plus Untargeted Metabolomics Pro
Figure 7 Number of total identifications of Untargeted Metabolomics Plus and Pro
Figure 8 Number of level1 identifications of Untargeted Metabolomics Plus and Pro
Untargeted Metabolomics Plus is labeled in orange, while Untargeted Metabolomics Pro is labeled in green.
Key Advantages of Untargeted Metabolomics Plus and Pro
Database: A high-quality secondary spectral database including in-house standard database (18,000+ standards) and in-house secondary spectrum library, ensuring comprehensive and high-quality search results.
Deliverables: High identification accuracy (Level1:1200+);
A significantly increased number of identifications (total exceeding 7,000 compounds);
Bioinformatics Analysis: Comprehensive and diverse analytical points: Delivers 27 standard analytical results, with additional availability of multiple advanced analyses and correlation analysis services.
Recommended Strategies for Untargeted Metabolomics
Depending on research goals, we recommend untargeted metabolomics for customers who:
Require broad, untargeted screening with no specific compounds of interest.
Need accurate detection of specific target compounds.
Aim for preliminary screening in early stages and validation in later stages.
Work with animal or specialized samples and need relative quantification.
Depending on research areas, we recommend untargeted metabolomics for customers who:
Medical research
Main research direction
Subfield and expiation
Tumor research
Tumor mechanism and diagnosis
Drug treatment
Neurological diseases
Mechanism and treatment of Alzheimer's disease
Brain-Gut Axis Research
Autoimmune diseases
mechanism and biomarker of disease (Inflammatory Bowel Disease)
Gut microbiome
Metabolic disease
mechanism and biomarker of disease
(non-alcohol fatty liver disease, diabetes, obesity, Atherosclerosis，etc)
Agriculture and food science
Stress resistance
Understanding plant adaption under light, moisture, etc
Color phenotypes
Exploring molecular mechanisms behind pigment and taste
Customer Literature and Application Scenarios
Number
Title
Type of product
Application scenario
IF
Link
1
Mannose metabolism reshapes T cell differentiation to enhance anti-tumor immunity
Untargeted metabolomics
+Transcriptomics
Disease Pathogenesis and Therapeutic Interventions
48.8
10.1016/j.ccell.2024.11.003
2
A Copper/Ferrous-Engineering Redox Homeostasis Disruptor for Cuproptosis/Ferroptosis Co-Activated Nanocatalytic Therapy in Liver Cancer
Untargeted metabolomics
+Transcriptomics+Targeted metabolomics
Molecular Subtyping： cancer treatment
19
https://doi.org/10.1002/adfm.202402022
3
Metabolomics identifies phenotypic biomarkers of amino acid metabolism in milk allergy and sensitized tolerance
Untargeted metabolomics+ Targeted metabolomics
Disease diagnostic and prognostic markers： biomarker
14.2
10.1016/j.jaci.2024.02.023
4
Blautia Coccoides is a Newly Identified Bacterium Increased by Leucine Deprivation and has a Novel Function in Improving Metabolic Disorders
Untargeted metabolomics+ Transcriptomics
Gut Microbiota Study
14.1
10.1002/advs.202309255
5
Microbiota-derived lysophosphatidylcholine alleviates Alzheimer’s disease pathology via suppressing ferroptosis
Untargeted metabolomics
+ Transcriptomics
Mechanism and treatment of Alzheimer’s disease
31.2
10.1016/j.cmet.2024.10.006
6
Biochar reduces the cadmium content of Panax quinquefolium L. by improving rhizosphere microecology
Untargeted metabolomics+Microbiomics
Stress research
8
10.1016/j.scitotenv.2024.170005
## FAQ
- Can Untargeted Metabolomics provide absolute presence/absence data? A: Cannot provide a true sense of the presence or absence of metabolites.
The method involves missing value imputation. Even pre-imputation "detections" reflect instrument-selected presence (not biological reality). Non-detection may indicate either true absence or sub-threshold abundance filtered by software.
Possible reasons for missing target compounds in Untargeted Metabolomics identification?
- A: 1) Signal-to-noise ratio (S/N) cutoff (<3) eliminates low-abundance hits, so it's possible that these substances were identified, but the signal-to-noise ratio was insufficient to meet the screening criteria.
DDA mode is used for untargeted metabolomics secondary scanning, which selects the top 10 most abundant ions per scan. It is possible that the content of the substance is too low to be detected. Extraction methods optimize for the majority of metabolites, not specific compounds.
The scanning range for untargeted metabolism is m/z 100-1500, so if the substance of interest is not in the scanning range, it will not be identified (e.g, lower molecular weight lactate, pyruvate, etc).
- What is the recommended number of samples for untargeted metabolomics?
- A: The required sample size is determined by the number of experimental groups, sample category, and corresponding recommended biological replicates. For the minimum total sample size, untargeted metabolomics analysis generally requires at least 6 samples.
You can also refer to the recommended replicates number: at least 30 clinical samples per group, 10 animal model samples per group, and 6 plant samples per group.
What do “mass error” and “score” mean in the raw data file in result files?
- A:1)The mass error used during database searching is a user defined tolerance that specifies the allowable deviation between the experimentally mea sured m/z values and the theoretical m/z values in the reference database.This parameter is applied at the data analysis stage and is typically express ed in parts per million (ppm).A tolerance of 10~20 ppm is generally used for mass deviation of MS2 spectra. Since our database searching is based on MS2 spectral matching, using a 10ppm mass tolerance represents a highly reliable and appropriate setting for metabolomics analysis.
Reference: DOI: 10.1038/s41592-021-01331-z
2) The score represents the MS/MS (secondary mass spectrometry) spectral matching score between the detected metabolite and the reference compound in the database. It reflects the similarity of fragment ion patterns. A higher score indicates a better MS/MS match and higher confidence in metabolite identification.
We only retain metabolites with a score greater than 0.5. The definition and calculation process of this score are as follows: After comparing a large number of experimental secondary spectra against databases, the relationship between FDRs and spectral similarity was esta
blished. In the range where similarity scores exceed 0.5(Schymanski et al., 2014), the FDR data can be kept below 15 %Briefings in Bioinformatics, 20 24, 25(2): bbae056b), maintaining a relatively low level.
Is there a sample quality control (QC) step in untargeted metabolomics?
- A: No, metabolomics does not include a sample QC step. The detectability of metabolites in the customer’s samples can only be assessed after mass spectrometry analysis.
In metabolomics, QC samples are prepared by pooling equal volumes from the customer’s samples. These are prepared by the laboratory during the metabolite extraction stage and analyzed together with the samples. QC samples are used solely to monitor instrument stability and data quality and cannot be used to assess the quality of the individual samples.
- Can we accept extracted metabolites samples?
- A: We can accept extracted metabolites for untargeted metabolomics. However, the customer needs to provide detailed information about the extraction method, including the reagents used and the amounts applied during extraction. After evaluation, we will confirm whether the extracted metabolites can be accepted for analysis.
## Introduction to Quasi-targeted Metabolomics
- What is Quasi-targeted Metabolomics
Technical characteristicsHigh-throughputCompared to conventional targeted techniques, it supports qualitative characterization of a wider variety of compounds.High-sensitivityThe lower limit of detection enables the identification of trace compoundsAccurate QuantificationMRM-based quantification enables more accurate biomarker screening compared to untargeted approachesComprehensive coverageThe database provides comprehensive coverage of KEGG pathways, enabling efficient resolution of biological questionsTechnical characteristicsHigh-throughputCompared to conventional targeted techniques, it supports qualitative characterization of a wider variety of compounds.High-sensitivityThe lower limit of detection enables the identification of trace compoundsAccurate QuantificationMRM-based quantification enables more accurate biomarker screening compared to untargeted approachesComprehensive coverageThe database provides comprehensive coverage of KEGG pathways, enabling efficient resolution of biological questionsA novel metabolomics detection technology that combines the high-throughput advantages of untargeted metabolomics with the high accuracy and sensitivity of targeted metabolomics.
Technical characteristics
High-throughput
Compared to conventional targeted techniques, it supports qualitative characterization of a wider variety of compounds.
High-sensitivity
The lower limit of detection enables the identification of trace compounds
Accurate Quantification
MRM-based quantification enables more accurate biomarker screening compared to untargeted approaches
Comprehensive coverage
The database provides comprehensive coverage of KEGG pathways, enabling efficient resolution of biological questions
Technical characteristics
High-throughput
Compared to conventional targeted techniques, it supports qualitative characterization of a wider variety of compounds.
High-sensitivity
The lower limit of detection enables the identification of trace compounds
Accurate Quantification
MRM-based quantification enables more accurate biomarker screening compared to untargeted approaches
Comprehensive coverage
The database provides comprehensive coverage of KEGG pathways, enabling efficient resolution of biological questions
Project workflow of Quasi-targeted Metabolomics
The project workflow for Quasi-targeted Metabolomics is similar to Untargeted Metabolomics. For detailed information, please refer to the workflow described in the Untargeted Metabolomics section.
Sample Collection and Requirements
The sample collection and requirements for Quasi-targeted Metabolomics is similar to Untargeted Metabolomics. For detailed information, please refer to the workflow described in the Untargeted Metabolomics section.
Data Acquisition
Acquisition Parameters
Service
Quasi-targeted Metabolomics
Scan mode
MRM mode Q1: parent ion Q3: product ion
Ion mode
Positive+Negative
Run time
15min
Column
HSS T3 column
MS platform
SCIEX QTRAP 6500+
Process of LC-MS detection
Figure 9 Process of LC-MS detection and QC preparation method of Quasi-targeted Metabolomics
*Note: Quasi-targeted metabolomics adds isotopically labeled standards to experimental samples, improving the accuracy of both qualitative and quantitative results.
## Data Preprocessing and Analysis
In-house Quasi-targeted Metabolomics Database
The quasi-targeted metabolomics database consists entirely of reference standards, with all identifications at Level 1. The database is organized into animal and plant categories.
Animal& human database
Category
Quantity
Representative Compounds
Amino Acids & Derivatives
290+
Lysine, proline, histidine, isoleucine, tyrosine
Organic Acids & Derivatives
200+
Citric acid, succinic acid, maleic acid, glyoxylic acid, cis-Aconitic acid
Nucleosides/Nucleotides
150+
ATP, GDP, UDP, GMP, NADH, FMN
Benzene Derivatives
350+
Phthalic acid, hippuric acid, syringic acid, p-Toluic acid
Bile Acids
80+
Cholic acid, lithocholic acid, chenodeoxycholic acid, glycocholic acid, ursodeoxycholic acid
Phenols/Amines
150+
Histamine, TMAO, dopamine, oxamic acid, 4-Nitrophenol
Sugars/Alcohols/Ketones
200+
Lactose, Ribose, Sorbitol, Trehalose, Rhamnose
Fatty Acids
130+
Decanoic acid, myristoleic acid, Palmitoleic acid, DHA
Lipids
300+
Glycerophosphocholine, monolaurin, malonylcarnitine, hexanoylcarnitine
Hormones
100+
Testosterone, corticosterone, cortisone, aldosterone, androstenedione, prostaglandins
Indoles & Derivatives
60+
Melatonin, serotonin, IAA, indole, tryptophol
Others
500+
Xanthurenic acid, pyridoxal, urocanic acid, imidazole, picolinic acid
Total
2500+
Plant database
Category
Quantity
Representative Compounds
Amino Acids & Derivatives
350+
Tyrosine, glutamine, citrulline, methionine, theanine
Organic Acids & Derivatives
300+
Citric acid, oxalic acid, succinic acid, trans-Aconitic acid, glyoxylic acid
Nucleosides/Nucleotides
100+
ATP, GMP, GDP, FMN, UDP, Cyclic AMP
Flavonoids
700+
Naringenin, kaempferol, rutin, glycitein, quercetin
Coumarins & Derivatives
200+
Coumarin, osthole, daphnetin, esculetin, imperatorin
Lignans
100+
Silymarin, stepharine, forsythin, sesamin
Alkaloids
200+
Lycorine, camptothecin, catharanthine, berberine, piperine
Terpenoids
700+
Polygalacic acid, ginsenosides, notoginsenosides, cryptotanshinone, paclitaxel
Phenols/Amines
450+
Caffeic acid, cinnamic acid, ferulic acid, ellagic acid, sinapyl alcohol
Sugars/Alcohols
400+
Lactose, xylitol, mannitol, xylose, fructose-6-phosphate
Plant Hormones
70+
Indole-3-acetic acid, abscisic acid, salicylic acid, jasmonic acid, zeatin, gibberellins
Lipids
450+
Cucurbitacins, lactobionic acid, linolenyl alcohol, paridisides, mogrosides
Others
1000+
Nicotinic acid, nicotinamide, pyridoxal, sulforaphane, brassinin
Total
5000+
Number of Level1 Detection
Human&animal sample total identification1200104610008038558268288538228007666004002000FecalHeartLiverSpleenLungKidneyBrainTesticleHuman&animal sample total identification1200104610008038558268288538228007666004002000FecalHeartLiverSpleenLungKidneyBrainTesticle
Human&animal sample total identification
1200
1046
1000
803
855
826
828
853
822
800
766
600
400
200
0
Fecal
Heart
Liver
Spleen
Lung
Kidney
Brain
Testicle
Human&animal sample total identification
1200
1046
1000
803
855
826
828
853
822
800
766
600
400
200
0
Fecal
Heart
Liver
Spleen
Lung
Kidney
Brain
Testicle
Figure 10 Total identification of human&animal sample of Quasi-targeted Metabolomics
## BI analysis
Figure 11 BI analysis of Quasi-targeted Metabolomics
Analysis Content
Standard Analysis
Software
Qualitative and quantitative analysis of metabolites
Sciex OS
Data quality control
metaX
Metabolite classification and pathway annotation
KEGG,HMDB,LIPIDMaps database
Differential metabolites screening*
metaX
Differential metabolite analysis
R language
KEGG enrichment analysis
R language, KEGG database
GSEA analysis
GSEA program
ROC curve analysis of differential metabolites
R language
*Note: If biological replicates are less than 3, PCA and PLS-DA analysis will not be performed.
## FAQ
- What is quantitative method of Quasi-targeted Metabolomics?
- A: Quasi-targeted Metabolomics uses a relative quantification approach.
- How to choose between untargeted and quasi-targeted metabolomics?
Figure 12 How to choose between Untargeted and Quasi-targeted Metabolomics
## Introduction to Targeted Metabolomics
- What is Targeted Metabolomics
Targeted metabolomics focuses on quantifying a defined group of metabolites in biological samples to gain precise insights into metabolic activities. In contrast to untargeted metabolomics, which surveys a wide range of metabolites, the targeted approach concentrates on selected compounds of interest, making it particularly suitable for investigating specific pathways or biomarkers. With its high sensitivity, specificity, and reproducibility, targeted metabolomics serves as a powerful tool in areas such as biomarker identification, drug discovery, and elucidation of disease mechanisms.
Novogene’s Targeted metabolomics focuses on the specific and selective detection of predefined metabolites using reference standards. The analysis is typically performed on an LC-MS platform under multiple reaction monitoring (MRM) mode, where quantification is achieved through standard curves and corrected using isotope-labeled internal standards.
## Workflow of Targeted Metabolomics
Figure 13 Workflow of Targeted Metabolomics
Targeted Metabolomics Products
Product
Number of metabolites
Metabolite name
Biological Functions
Application area
Applicable sample types *
Amino acid
23
Glycine, Alanine, Valine, Leucine, Isoleucine, Phenylalanine, Tryptophan, etc.
Constituents of proteins and peptides; maintenance of internal homeostasis; regulation of glucose and lipid metabolism
Plant growth/development, stress resistance, senescence; Human cardiovascular diseases, diabetes, cancer research
Blood, Animal/Plant Tissues, Cells
Fatty Acids
50
Hexanoic acid, Octanoic acid, Decanoic acid, Undecanoic acid, Dodecanoic acid (Lauric acid), etc.
Components of biological membranes; major energy source; crucial for growth/development; key signaling molecules in plant-microbe interactions
Plant stress resistance, growth, energy metabolism; Plant-microbe interactions
Feces, Animal Tissues, Plant Tissues (e.g., pulp, fruit with high lipid content)
Central Carbon Metabolism-related Substances
34
Metabolites from TCA cycle, Glycolysis, Pentose Phosphate Pathway, Oxidative Phosphorylation, Purine Metabolism, etc.
Fundamental basis for life activities in animals and plants
Growth/development, Tumor metabolic reprogramming, Energy metabolism, Immunity
Plant Tissues, Animal and Clinical Samples
Organic Acids
13
Itaconic acid, Citric acid, Malic acid, Succinic acid, Fumaric acid, α-Ketoglutaric acid, etc.
Key components of the TCA cycle; involvement in energy metabolism and immune regulation
Energy metabolism, Cancer research, Immunology
Serum/Plasma, Body Fluids, Animal/Plant Tissues, Cells
Bile Acids
72
Glycocholic acid, Glycochenodeoxycholic acid, Taurocholic acid, etc.
Regulate enterohepatic circulation; hepatoprotective effects; involvement in glucose/lipid metabolism homeostasis; immunomodulation
Gut microbiota & immunity, Metabolic diseases, Gastrointestinal disorders
Feces/Intestinal contents, Animal tissues, Serum
Tryptophan Metabolism
44
Tryptophan, Kynurenine, Indole-3-acetic acid, Serotonin (5-HT), Xanthurenic acid, etc.
Protein biosynthesis; immunoregulation; association with various diseases
Cancer, Neurological disorders, Digestive system diseases
Serum, Feces, Animal tissues
Short-Chain Fatty Acids (SCFAs)
11
Acetic acid, Propionic acid, Butyric acid, Isobutyric acid, Valeric acid, Isovaleric acid, Hexanoic acid, etc.
Gut microbiota metabolites; regulate glucose/lipid metabolism; anti-inflammatory; anti-tumor properties
Gut microbiota research, Immunology, Glucose/lipid metabolic disorders
Feces, Animal tissues, Serum
N500
500
Fatty acids,Short-chain fatty acids,Indole,Organic acid,Amino acids etc
Metabolic disease
Serum/Plasma,Ani mal/plant tissue
*Note: For products not listed in the price list, or if a customer is interested in a compound not included in the product, please contact the APM team.
* Only China lab can do pretreatments for all sample types listed above for targeted metabolomics products.
## BI Analysis
Analysis Content
Standard Analysis
Software
Standard curve and linear range
Total ion chromatogram
QC evaluation and sample quantification results
Differential metabolite analysis
R language
KEGG pathway annotation
KEGG PATHWAY database
ROC curve analysis of differential metabolites
R language
Comparing Metabolomics Services and Choosing the Right Option
Type of services
Untargeted Metabolomics
Quasi-targeted Metabolomics
Targeted Metabolomics
Scan Mode
DDA
Scheduled MRM
MRM
Database
In-house standard library & public MS/MS spectral library (170,000+)
Plant: 5.000+ Human & Animal: 2,500+
Full standard library
Methods established using standards; distinct detection methods developed for different metabolite classes
Quantitative Analysis
Peak area integration (Relative Quantification)
Internal standard method (Absolute Quantification)
Key Features
Unbiased broad screening, identifies the highest number of compounds Cost-effective, shorter turnaround time, suitable for initial screening stages
Improved quantification accuracy, enhanced detection of low-abundance metabolites (compared to untargeted)
Detects more compounds than targeted approaches
Highest quantitative accuracy, provides absolute metabolite concentrations
Highly specific, ideal for validation phases of research
Figure 14 Comparing Metabolomics Services and Choosing the Right Option
## Multi-omics Analysis
Metabolomics can be integrated with transcriptomics, microbiomics, and proteomics for correlation analysis. The integration with proteomics is managed by the proteomics team.
Parallel Research Framework of Multi-omics Research
Figure 15 Parallel research framework of multi-omics research
Significance of Multi-omics Integration
More accurate - Compensates for data noise and missing factors in single-omics analysis
More reliable - Cross-validation between multi-omics data reduces false positives
Deeper insights - Joint analysis reveals multi-level mechanisms and phenotype-genotype linkages
Demo Results for Metabolomics- transcriptomics and Metabolomics- microbiomics Integration Analysis
For demo reports or related details, please refer to the AMEA WeDrive folder https://drive.weixin.qq.com/s?k=AJgAAQcaAAwtPXtifq or contact the APM team.
## Appendix
Bioinformatic Analysis Form for Metabolomic Project
This table is a BIF form for metabolic products. All metabolic products use the same BIF form, and only the specific product name needs to be modified. Link: https://drive.weixin.qq.com/s?k=AJgAAQcaAAwzkg2R24
Note
All services are for Research Use Only. Not for Clinical Diagnostic Use.
Selected Publications Mentioning Novogene
Published Year
Application
Journal IF
Title
2025
Chem
19.1
Beyond natural synthesis via solar-decoupled biohybrid photosynthetic system
2025
ACS Nano
15.8
Inflammatory Microenvironment-Responsive Microsphere Vehicles Modulating Gut Microbiota and Intestinal Inflammation for Intestinal Stem Cell Niche Remodeling in Inflammatory Bowel Disease
2025
Advanced Science
14.3
Quercetin-Driven Akkermansia Muciniphila Alleviates Obesity by Modulating Bile Acid Metabolism via an ILA/m6A/CYP8B1 Signaling
2025
JOURNAL OF CLINICAL INVESTIGATION
13.3
Lactobacillus rhamnosus GG induces STING-dependent IL-10 in intestinal monocytes and alleviates inflammatory colitis in mice
2025
JOURNAL OF HAZARDOUS MATERIALS
12.2
Boron-induced phenylpropanoid metabolism, Na+/K+ homeostasis and antioxidant defense mechanisms in salt-stressed soybean seedlings
2025
WATER RESEARCH
11.4
Effect of pre-chlorination on bioelectricity production and stabilization of excess sludge by microbial fuel cell
2025
JOURNAL OF EXPERIMENTAL & CLINICAL CANCER RESEARCH
11.4
CYP3A5 promotes glioblastoma stemness and chemoresistance through fine-tuning NAD+/NADH ratio
2025
GENOME BIOLOGY
10.1
Systematic interrogation of functional genes underlying cholesterol and lipid homeostasis
2024
CANCER CELL
48.8
Mannose metabolism reshapes T cell differentiation to enhance anti-tumor immunity
2024
Cell Metabolism
27.7
Microbiota-derived lysophosphatidylcholine alleviates Alzheimer’s disease pathology
via suppressing ferroptosis
2024
Cell Metabolism
27.7
Stress triggers irritable bowel syndrome with diarrhea through a spermidine-mediated decline in type I interferon
2024
Cell Metabolism
27.7
A clinical-stage Nrf2 activator suppresses osteoclast differentiation via the iron-ornithine axis
2024
Cell Host & Microbe
20.6
Gut symbiont-derived anandamide promotes reward learning in honeybees by activating the endocannabinoid pathway
2024
Nature Microbiology
20.5
Taurolithocholic acid protects against viral haemorrhagic fever via inhibition of ferroptosis
2024
ADVANCED FUNCTIONAL MATERIALS
18.5
A Copper/Ferrous-Engineering Redox Homeostasis Disruptor for Cuproptosis/Ferroptosis Co-Activated Nanocatalytic Therapy in Liver Cancer
2024
ACS Nano
15.8
Oral Propolis Nanoemulsions Modulate Gut Microbiota to Balance Bone Remodeling for Enhanced Osteoporosis Therapy
Novogene Product Manual
Proteomics Service
AMEA 2025.12
(This product manual is strictly confidential and intended solely for internal use within the AMEA region. The contents must not be shared with any external parties without prior written approval from the APM Director. For any product-related inquiries, please contact the APM Team.)
Product Manual Revisions
Subject
Novogene Product Manual- Proteomics Service
Revision Number
2025 V1.0
Issue Date
Dec, 2025
Prepared by
Zhang Yuebai
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
Contents
Proteomics Service Overview7
Basic Concepts in Proteomics8
## Introduction to LC-MSMS8
- What is Proteome?10
- What is Proteomics?10
- What is Label-free or Label-based Quantification in Proteomics?11
The Acquisition Modes of Proteomics12
What do We Get from Raw Data?13
The Principal of Searching15
The Selection of Database16
## Introduction to Quantitative proteomics17
- What is Quantitative Proteomics17
## Workflow of Quantitative Proteomics17
## Sample Requirements and Guidelines18
Acquisition Parameters in Quantitative Proteomics20
BI Analysis21
Project Experience in Novogene22
Key Advantages of Quantitative Proteomics24
Application for Quantitative Proteomics25
Customer Literature and Application Scenarios25
Case Study26
## FAQ29
## Introduction to Qualitative Proteomics32
- What is Qualitative Proteomics32
## Workflow of Qualitative Proteomics32
## Sample Requirements and Guidelines32
Acquisition Parameters in Qualitative Proteomics33
BI Analysis33
Application for Qualitative Proteomics34
Customer Literature and Application Scenarios35
Case Study35
## FAQ37
## Introduction to PRM Proteomics (AMEA haven’t launch)38
- What is PRM Proteomics38
## Workflow of PRM Proteomics38
## Sample Requirements and Guidelines40
Acquisition Parameters in PRM Proteomics40
Data Preprocessing and Analysis40
Key Advantages of PRM Proteomics in Novogene41
Application for PRM Proteomics43
Case Study43
## FAQ45
## Introduction to PTM Proteomics46
- What is PTM Proteomics46
Phosphoproteomics46
Acetylproteomics47
Ubiquitinomics47
N/O-glycoproteomics48
Lactylproteomics (AMEA haven’t launch)49
## Workflow of PTM Proteomics50
## Sample Requirements and Guidelines52
Acquisition Parameters in PTM Proteomics52
Data Preprocessing and Analysis53
BI Analysis56
Project Experience in Novogene57
Key Advantages of PTM Proteomics in Novogene58
Application for PTM Proteomics60
Customer Literature and Application Scenarios60
Case Study61
## FAQ64
Multi-omics Analysis65
Why should We Include Proteomics in Multi‑omics Research?65
Parallel Research Framework of Multi-omics Research67
Demo Results for Proteomics - Transcriptomics and Proteomics – Metabolomics Integration Analysis67
Appendix68
Supplementary Knowledge on Protein Research68
Basic Information of Protein68
Western Blot70
IP/Co-IP70
Elisa72
Flow Cytometry72
Note73
Reference73
## Proteomics Service Overview
Service type
Minimum sample requirement and replicates
Equipment used
Data format
Turnaround time
Lab location for sample pretreatment
Quantitative proteomics
Thermo Scientific Orbitrap Astral
.raw
35 working days
(<100 samples)
Singapore / TJ
Qualitative proteomics
Minimum 6 samples per project per batch.
Thermo Scientific Orbitrap Astral (start from Jan 1st, 2026)
.d
35 working days
(<100 samples)
TJ
PRM proteomics
≥ 3 replicates are highly
recommended
Thermo Scientific Orbitrap Astral
.raw
50 working days
(<100 samples)
TJ
PTM proteomics
Thermo Scientific Orbitrap Astral; Thermo Q ExactiveTM HF-X
.raw
35 working days
(<30 samples)
TJ
- Note:
Sample requirements and preparation method, please refer to the link: Novogene-AMEA-Sample-Submission-Guideline_Mass-Spectrometry-2025-03-V1.pdf
Basic Concepts in Proteomics
## Introduction to LC-MSMS
The experimental workflow of proteomics primarily includes sample collection, protein extraction and digestion, instrumental analysis, and data processing. Proteins exhibit inherent characteristics - including rapid turnover, extensive diversity, post-translational modifications, and high data complexity - that can introduce variability at every stage of proteomic analysis. From sample collection and preservation to protein extraction and mass spectrometric detection, each step critically influences data quality and reproducibility, thereby directly affecting the reliability of downstream bioinformatic analyses.
To ensure the accuracy and reliability of the data at source, Novogene implements quality control at every experimental stage, establishing standardized proteomic protocols to guarantee the output of high-quality data.
Figure 1 The workflow of MS-based protein identification
Figure 2 The detail of Orbitrap Astral
- Note:
HPLC (High performance liquid chromatography):
To separate the complex peptide mixture before it enters the mass spectrometer.
ESI (Electrospray ionization):
Facilitates the ionization of dissolved peptides, generating gas-phase ions for subsequent mass measurement within the spectrometer.
Quadrupole mass analyzer:
To act as a mass filter, selecting ions of a specific mass-to-charge ratio (m/z) to pass through to the next stage.
MS1 (First mass, Orbitrap mass analyzer):
To perform the initial survey scan to measure the mass-to-charge ratios (m/z) and abundance of all intact peptide ions entering the mass spectrometer at that moment.
MS2 (Second mass, Astral mass analyzer):
To isolate a specific precursor ion from the MS1 scan, fragment it, and measure the m/z of the resulting fragment ions to determine the peptide's amino acid sequence.
m/z (mass-to-charge ratio):
m/z stands for mass-to-charge ratio. It is a fundamental parameter used to characterize ions and is central to how mass spectrometers identify and measure ions.
- What is Proteome?
The proteome is defined as the entire set of proteins expressed by a cell, tissue, or organism at a specific time and under defined conditions.
Dynamic - constantly changing in response to external signals
Diverse -– type, amount, post-translational modifications……
Complex - alternative splicing, various post-translational modifications (PTM)……
​
- What is Proteomics?
Proteomics is a useful scientific tool for large-scale study of the proteome - the entire complement of proteins in a biological system. By analyzing protein expression, modifications, interactions, and functions, this field provides critical insights with substantial value for both basic science and practical applications.
As the combination of primary executors, proteomics can provide more effective information for the discovery of biomarkers, drug targets, etc.
Figure 3 Proteomics: a powerful tool for the post-genomic era
- What is Label-free or Label-based Quantification in Proteomics?
FeatureLabel-free proteomicsLabel-based proteomicsSample PreparationSimpler, less time-consumingMore complex, requires labeling stepCostLower, no labeling reagents neededHigher, due to labeling reagentsFeatureLabel-free proteomicsLabel-based proteomicsSample PreparationSimpler, less time-consumingMore complex, requires labeling stepCostLower, no labeling reagents neededHigher, due to labeling reagentsProteomics is a key area of research that involves the large-scale study of proteins and their functions. As the field grows, two major techniques have emerged for protein quantification: label-free proteomics (LFQ) and label-based proteomics (TMT, iTRAQ, SILAC).
Feature
Label-free proteomics
Label-based proteomics
Sample Preparation
Simpler, less time-consuming
More complex, requires labeling step
Cost
Lower, no labeling reagents needed
Higher, due to labeling reagents
Feature
Label-free proteomics
Label-based proteomics
Sample Preparation
Simpler, less time-consuming
More complex, requires labeling step
Cost
Lower, no labeling reagents needed
Higher, due to labeling reagents
Proteome Coverage
Higher
Lower, due to increased sample complexity
Multiplexing
Limited, separate runs for each sample
High, limited by the number of labels
Quantification Accuracy
Moderate
Higher
Dynamic Range
Wider
Narrower
Machine Time
More
Less
Data Analysis Complexity
High
LFQ is a mass spectrometry-based analytical technique that facilitates the relative quantification of proteins by directly analyzing the mass spectrometric signals, such as ion chromatogram peak intensities or spectral counts, of proteolytic peptides within the sample. This approach obviates the need for isotopic labeling or chemical modifications. The principal advantages of LFQ include streamlined sample processing, reduced costs, and its suitability for high-throughput analysis across a wide array of samples. In Novogene, quantitative proteomics services are based on LFQ.
The Acquisition Modes of Proteomics
The acquisition modes of proteomics can be divided into two strategies: DDA and DIA.
DDA (Data-dependent acquisition): collect strong and high-abundance peptide ions within each time window during primary mass spectrometry, which are then subjected to fragmentation analysis during secondary mass spectrometry.
DIA (Data-independent acquisition): Divide the entire full scanning range of mass spectrometry into several windows, and cycle all ions in each window for selection, fragmentation, and detection. In DIA, all precursor ions in a predefined isolation windows based on m/z are isolated to acquire multiplexed MS2 spectra, and this step is repeated until the full mass range is covered. This unbiased approach ensures comprehensive coverage, enhanced reproducibility, and superior quantification across complex proteomes.
Library-free DIA enhances the capability of traditional DIA, which relies on narrow isolation windows, by reducing or eliminating co-isolation interference. This results in cleaner MS2 spectra and eliminates the need for a DDA-based reference library. At Novogene, our quantitative and PTM proteomics services are based on this library-free DIA platform.
Figure 4 The diagram of DDA, DIA and Deep/Rapid DIA
What do We Get from Raw Data?
In proteomics, the amino acid sequence of a peptide is not directly determined from the raw data, which consists of a series of complex mass spectra. Instead, the sequence is elucidated by searching the MS1 and MS2 data against a protein database. Furthermore, the quantification of proteins and peptides is typically based on the information derived from the MS2 spectra.
MS1 - TIC (upper): total ion current (TIC) represents the chromatogram of all ions in the sample.
MS1 - spectrum (mid): The full MS1 survey scan (e.g., at RT=12.82 min) detects the total precursor ions present at that specific retention time. In a following DIA step, these precursors are covered by 300 isolation windows.
MS2 - spectrum (lower): The raw MS/MS spectrum (e.g., RT=12.46, m/z=543.4964) shows the detected fragment ions as isolated, unassigned peaks. The peptide sequence can only be identified by matching these peaks to the theoretical fragments derived from a candidate peptide sequence.
Figure 5 The figures of raw data
The Principal of Searching
In Novogene, proteome analysis is based on bottom-up analysis relied on database. Bottom-up proteomics involves in the proteolytic digestion of proteins before analysis by mass spectrometry. The term bottom-up implies that information about the constituent proteins is reconstructed from individually identified fragment peptides.
The basic process is that the protein mixture is digested into a peptide mixture. After the peptide mixture is chromatographed and ionized, the peptide fragment fingerprints are generated by tandem mass spectrometry for peptide identification. Proteins are finally identified from the peaks of the captured mass spectra using computational methods, where each peak theoretically represents a peptide fragment ion. The database search approach is a common method for mass-based protein identification methods.
The database search approach identifies proteins by generating theoretical spectra in silico from a given protein sequence database and comparing experimental spectra with the theoretical ones to find the closest matches.
Figure 6 The workflow of database searching
The Selection of Database Database Selection
The UniProt database, particularly its expertly curated Swiss-Prot section, is the most recommended resource. If a subsequent integrative analysis with transcriptomic data is planned, it is crucial to ensure compatibility between the protein and gene identifiers. For this purpose:
For reference-based transcriptome analysis, use the corresponding protein database from NCBI
For non-reference transcriptome analysis, use the custom protein database annotated from the assembled transcriptome
Species Selection
The primary choice should always be a public database specific to the species of the experimental samples. If a dedicated database is unavailable, the recommended alternatives are to:
Generate a species-specific protein database via transcriptome sequencing and annotation
Select a database from a closely related species
In the case of specific organisms like phages and bacteria, protein identification and subsequent analysis are often compromised by constraints in database size and quality.
## Introduction to Quantitative proteomics
- What is Quantitative Proteomics
Quantitative proteomics aims to systematically determine the expression levels of proteins, and perform accurate quantitative comparisons. Quantitative proteomics is a branch of proteomics that involves the identification and quantification of proteins in a sample, often using techniques like mass spectrometry. It allows researchers to compare the abundance of proteins between different samples, such as cells in a healthy state versus cells under disease conditions.
## Workflow of Quantitative Proteomics
The standard proteomics workflow encompasses protein extraction, digestion, desalting, instrumental analysis, and data processing.
As each step - from sample preparation to mass spectrometry - can impact data quality and the validity of subsequent bioinformatic analysis, Novogene implements rigorous quality control and standardized protocols at every stage to ensure the generation of highly accurate and reliable data from the source.
Novogene currently offers two quantitative proteomics services based on different gradient time: Deep DIA (24 min) and Rapid DIA (8 min).
For blood samples (plasma/serum), Novogene offers an optional pretreatment service to deplete high-abundance proteins. The gradient time for blood proteomics (Thermo kit-based depletion) is 15 minutes*, and the product in quotation is based on Deep DIA.
* Due to the inherent properties of the Thermo depletion kit, extending the gradient time is unlikely to yield significant improvements in results. For projects requiring nanoparticle-based enrichment of low-abundance proteins, please consult the APM team for a case-specific evaluation.
Figure 7 The workflow of quantitative proteomics (Deep/Rapid DIA)
Figure 8 The workflow of quantitative proteomics (blood sample)
## Sample Requirements and Guidelines
The SG lab can accept the below sample types for quantitative proteomics services.
Sample type
Deep/Rapid DIA
Animal tissue*
Soft tissue (brain, heart, liver, spleen, lung, kidney, muscle, etc.)
10 mg
Tough tissue (hair, cartilage, etc.)
200 mg
Cell**
Suspension/adherent cultured cells
2×106 (10 μL cell pellet)
Serum/Plasma
No high-abundant protein depletion procedure
5 μL
High-abundant protein depletion from human blood by kit***
10 μL
Body Fluids****
Cerebrospinal fluid/Semen/ Follicular Fluid/Saliva/Tear
500 μL
Urine
10 mL
Breast milk
10 μL
Extracted protein sample***** (Solvent buffer
Non-detergent containing protein sample (Optimal buffer with
6M Urea, preferred protein concentration ≥ 0.5 μg/μL)
100 μg
reagent components
must be provided)
Detergent containing protein sample (including SDS, triton X-100, NP40, CHAPS, etc.)
200 μg
For more details about sample requirements and preparation method, please click the link: Novogene-AMEA-Sample-Submission-Guideline_Mass-Spectrometry-2025-03-V1.pdf.
- Note:
* It is recommended that customers provide samples according to the above quantities to ensure the smooth execution of the project. If the submitted sample quantity is lower than the recommended amount, an inquiry evaluation is required, and customers need to be informed of the associated risks.
** Please ensure the cell count can meet the requirement.
*** For non-human blood samples, please reach out to the APM team to facilitate evaluation and pricing.
**** Body fluid samples generally have low protein content, so it is recommended to avoid dilution and send us the undiluted samples whenever possible.
***** When the sample type is a protein solution or protein powder, SDS-PAGE gel image and protein quantification results must be provided to confirm the protein extraction efficiency. If the buffer contains detergents or the protein concentration is below 0.5 μg/μL, protein purification/ concentration is necessary. This process may result in protein loss, so a significantly larger sample amount is required.
Acquisition Parameters in Quantitative Proteomics
Service
Deep DIA
Rapid DIA
Blood sample
Scan mode
DIA (data-independent acquisition)
Run time
24 min
8 min
15 min
MS platform
Thermo Orbitrap Astral
Searching software
DIA-NN
Database
Swissprot for human and mice sample, Uniprot, NCBI, etc.
## BI Analysis
Figure 9 Process of BI analysis of quantitative proteomics
Analysis Content
Standard Analysis
Software/Content
Qualitative and quantitative analysis
DIA-NN (software)
Data quality control
Peptide length, Protein coverage, Peptide length, Protein coverage, etc
Protein functional annotation
GO, Domain, KEGG, IPR, Subcellular localization, Transcription factor
Differential protein expression analysis*
Volcano plot, HCA analysis, K-means clustering, Differential proteins selection
Differential enrichment analysis
GO, KEGG, IPR, etc
GSEA analysis
GSEA-GO, KEGG, IPR, subcellular localization
PPI analysis
Differential proteins PPI analysis
- Note: *If biological replicates are less than 3, differential protein expression analysis (except differential proteins selection) will not be performed. For more details, please check with demo report: https://drive.weixin.qq.com/s?k=AJgAAQcaAAw1Y1kBlg
Project Experience in Novogene
Figure 10 Identified proteins in different sample types (Deep DIA)
Figure 11 Identified proteins in different sample types (Rapid DIA)
Figure 12 Identified proteins in trace or complicated samples (Deep DIA)
Figure 13 Identified proteins in cohort projects (Deep DIA)
Key Advantages of Quantitative Proteomics
Instrumentation: Thermo Orbitrap Astral
Bioinformatics analysis: Comprehensive and diverse analytical points, ranging from functional annotation and pathway enrichment to protein-protein interaction.
Experience in cohort studies: Integrating the advantages of higher throughput and deeper coverage of the Astral platform, breaking through the limitations of traditional detection, facilitating the development of cohort studies.
Application for Quantitative Proteomics
We recommend this service if customers goal is to:
Discover biomarkers & drug targets: Conduct broad, untargeted screening of proteome profiles to identify differentially expressed proteins with potential.
Elucidate disease mechanisms: Compare protein abundances between diseased and healthy states to uncover the molecular drivers of pathogenesis.
Map signaling pathways: Perform preliminary discovery-phase analysis to investigate dynamic changes in cellular signaling networks and pathway activities.
Customer Literature and Application Scenarios
No.
Title
Service
Application scenario
IF
DOI
1
Jute Nanocrystalline Cellulose Relieves Polystyrene Nanoplastic-Induced Acute Injuries by Modulating Gut Microbiota Gilliamella apicola
Deep DIA
Environmental toxicology
16
doi: 10.1021/acsnano.5c04210
2
An endoscopy deliverable hydrogel dry powder for sealing and repairing gastric perforation
Deep DIA
Biomedical engineering
9.6
doi: 10.1016/j.actbio.2025.08.056
3
ANG secretion predisposes endothelial cells toward angiogenesis in FIN56-induced ferroptotic hepatocellular carcinoma via the BMP6/ID1 signaling pathway
Deep DIA
Oncology, Molecular biology
8.2
doi: 10.1016/j.freeradbiomed.202 5.06.029
4
Glucose-induced glycation enhances the foaming properties of Trichosanthes kirilowii seed protein isolate: Insights into structure, interfacial behavior, and proteomics
Deep DIA
Diabetes, Traditional Chinese medicine
12.4
doi: 10.1186/s12906-017-1578-6
Case Study
Combined therapy with DR5-targeting antibody-drug conjugate and CDK inhibitors as a strategy for advanced colorectal cancer
Journal Publication: Cell Reports Medicine
Impact Factor: 11.7
Date of Publication: 2025 June
Research Background:
Colorectal Cancer (CRC), ranking as the third most prevalent malignant tumor globally and the second leading cause of cancer-related deaths, faces multiple clinical challenges: its insidious early symptoms often lead to delayed diagnosis, high metastatic propensity, frequent post-treatment recurrence, significant drug resistance, and severe treatment-related complications. These factors collectively contribute to the limited efficacy of existing treatment regimens and poor patient prognosis. Thus, breaking through the limitations of conventional therapeutic models and developing novel precision treatment strategies have become urgent priorities in current colorectal cancer research.
Research Conclusion:
This study represents the first demonstration of the synergistic therapeutic mechanism between Oba01, a novel DR5-targeting antibody-drug conjugate, and CDK inhibitors in colorectal cancer. The findings offer a highly translatable novel treatment strategy for this clinically challenging tumor type, while preliminary proteomics and multi-omics integrated analyses have elucidated the underlying mechanism of this synergistic therapeutic approach.
Study Design
Plasma proteome variation and its genetic determinants in children and adolescents
Journal Publication: Nature Genetics
Impact Factor: 29
Date of Publication: 2025 January
Research Background:
The global childhood obesity epidemic is worsening, accompanied by rising risks of diseases such as diabetes, metabolic syndrome, and fatty liver disease. The plasma proteome during growth and development is influenced by multiple factors, including genetics, age, sex, BMI, and puberty.
Current understanding of the dynamic changes in the proteome during childhood and its genetic regulation remains incomplete. Traditional affinity-based proteomics methods have limitations, whereas mass spectrometry-based proteomics offers high specificity and quantitative accuracy but is constrained in throughput and coverage. Thus, it is urgent to develop a streamlined and highly quantitative mass spectrometry-based proteomics workflow.
Research Conclusion:
This study represents the largest mass spectrometry-based investigation of the childhood plasma proteome to date, addressing a critical gap in our understanding of proteomic dynamics during development. It elucidates the systemic influences of genetics, age, sex, and BMI on the plasma proteome. The work provides a valuable resource for mechanistic studies of disease and drug target discovery, while underscoring the importance of accounting for genetic background in biomarker research.
Study Design
## FAQ
- Can quantitative proteomics in Novogene provide absolute expression level of proteins? A: Cannot provide absolute expression level of proteins.
Most standard proteomics workflows primarily provide relative quantification. This means they tell you how the abundance of a protein changes relative to another sample.
- How to deal with batch effect?
- A: Dealing with batch effects is a critical and unavoidable challenge in proteomics. A batch effect occurs when technical variations from sample processing, instrument runs, or reagent lots introduce systematic differences that are not due to biological conditions.
For multi-batch projects and cohort studies, it is recommended to use bridge samples.
A bridge sample is a single, homogeneous sample that is created by combining a small aliquot from every individual sample/group in a study. During initial sample preparation (first batch), a small portion is taken from each prepped biological sample and pooled together into a single vial. This creates the bridge sample. It is then analyzed repeatedly throughout the data acquisition process to act as a technical reference for normalization, quality control, and batch effect correction.
Each bridge sample is charged additionally, at a unit price based on the sample price.
- What is the recommended number of samples for quantitative proteomics?
- A: The required sample size is determined by the number of experimental groups, sample category, and corresponding recommended biological replicates. For the minimum total sample size, mass-based proteome analysis generally requires at least 3 samples.
A comparison of mass spectrometry-based proteomics and Olink.
- A: These two platforms are both cutting-edge technologies for proteome profiling. Mass spectrometry-based proteomics is typically used for discovery-level, untargeted analysis across multiple species, while Olink is designed for highly specific, targeted profiling in human studies. The table below summarizes the key differences between them.
Mass-based proteomics
Olink
Principle
DIA based on Thermo Astral platform
PEA (Proximity Extension Assay) technology converts protein signals into nucleic acid signals, detected via sequencing
Targeted/Untargeted
Untargeted
Targeted
Proteins number
Theoretically capable of profiling thousands to tens of thousands of proteins. The actual number of identified proteins is highly dependent on species, sample type, pretreatment methods
Depending on the selected panel
Species
Nearly all species (with a reference database)
Primarily human; limited panels for mouse
Sample type
All types
Blood and other body fluids
Advantages
Untargeted discovery
Broad species & sample applicability
Cost-effective for deep profiling
Capable of detecting PTMs
High specificity and sensitivity
Pre-validated panels for disease-focused research
Excellent for low-abundance proteins in biofluids
High throughput with minimal sample volume
## Introduction to Qualitative Proteomics
- What is Qualitative Proteomics
Qualitative Proteomics mainly focus on identification of proteins. Its core goal is to systematically identify protein types in biological samples. This technology can be used in various areas, such as identification of gel samples, analysis of proteins atlas, construction of protein-protein interaction networks. This technology can effectively answer "whether a certain protein exists in the sample".
## Workflow of Qualitative Proteomics
The project workflow for qualitative proteomics is similar to quantitative proteomics (Deep/Rapid DIA). Please refer to the 2.2 Workflow of Quantitative Proteomics in the quantitative proteomics section.
## Sample Requirements and Guidelines
The sample requirements and guidelines for qualitative proteomics are similar to quantitative proteomics. For detailed information, please refer to the
## Sample Requirements and Guidelines in the quantitative proteomics section.
Some other sample types are commonly used in qualitative proteomics, and submission guidelines are provided in the table below.
Sample type
Sample weight/volume
Gel*
Area < 1 cm2 (extra fee for larger areas)
Pure protein (best buffer is 6M Urea)
50 μg (concentration > 1 μg/μL)
Protein with loading buffer
50 μg (concentration > 1 μg/μL)
Beads (Protein A/G magnetic beads/Agarose beads - antigen-antibody complex)**
50 μg (estimation)
- Note: * For gel samples, obtaining clear, well-defined bands is critical. Coomassie Brilliant Blue stained bands have a higher probability of identifying target proteins than silver stained bands. The silver-stained gel must not contain glutaraldehyde. And ensure that the gel is cut and sent within one week after electrophoresis. Gel samples cannot be processed in SG lab so far.
** For beads sample, digestion can be performed either on-beads or after the proteins have been eluted from the beads. Beads sample cannot be processed in SG lab so far.
Acquisition Parameters in Qualitative Proteomics
Service
Qualitative proteomics
Scan mode
DIA
Run time
15 min
MS platform
Thermo Orbitrap Astral
Searching software
DIA-NN
Database
Swissprot for human and mice sample, Uniprot, NCBI, etc.
Standard AnalysisSoftware/ContentQualitative analysisDIA-NN (software)Standard AnalysisSoftware/ContentQualitative analysisDIA-NN (software)BI Analysis Analysis Content
Standard Analysis
Software/Content
Qualitative analysis
DIA-NN (software)
Standard Analysis
Software/Content
Qualitative analysis
DIA-NN (software)
Data quality control
Peptide length, Protein coverage, Peptide length, Protein coverage, etc
Protein functional annotation
GO, Domain, KEGG, IPR, Subcellular localization, Transcription factor
Figure 14 The workflow of qualitative proteomics
Application for Qualitative Proteomics
Establish a protein inventory: Answer the question, "What proteins are in this sample?" This is common for analyzing a new cell type, tissue, or biological fluid.
Characterize a protein complex: Identify all the member proteins that form a functional complex in a cell.
Identify proteins of interest: Discover which proteins are in a specific subcellular location (e.g., the nucleus or mitochondria) or which proteins bind to a drug or a DNA sequence.
Customer Literature and Application Scenarios
No.
Title
Service
Application scenario
IF
DOI
1
The Lactate-Primed KAT8-PCK2 Axis Exacerbates Hepatic Ferroptosis During Ischemia/Reperfusion Injury by Reprogramming OXSM-Dependent Mitochondrial Fatty Acid Synthesis
Qualitative proteomics
Hepatology, cellular metabolism
14.1
doi: 10.1002/advs.202414141
2
PIM1 instigates endothelial-to-mesenchymal transition to aggravate atherosclerosis
Qualitative proteomics
Cardiovascular disease, Pharmacology
13.3
doi: 10.7150/thno.102597
3
Base-modified nucleotides mediate immune signaling in bacteria
Qualitative proteomics
Microbiology, Immunology
45.8
doi: 10.1126/science.ads6055
4
Ribonuclease 1 Induces T-Cell Dysfunction and Impairs CD8+ T-Cell Cytotoxicity to Benefit Tumor Growth through Hijacking STAT1
Qualitative proteomics
Immunology, Oncology
14.1
doi: 10.1002/advs.202404961
Case Study
HPD is an RNA-Binding Protein Sustaining Ovarian Cancer Cell Glycolysis, Tumor Growth, and Drug Resistance
Journal Publication: Advanced Science
Impact Factor: 15.6
Date of Publication: 2025 August
Research Background:
HPD (4-hydroxyphenylpyruvate dioxygenase) is a key enzyme in the tyrosine catabolic pathway. Previous studies have shown that HPD exhibits aberrant expression and function in breast cancer, lung cancer, and liver cancer. Additionally, HPDL (4-hydroxyphenylpyruvate dioxygenase-like protein), a homolog of HPD, is a potential RBP (RNA-binding protein). So, does HPD also function as an RBP and participate in regulating ovarian cancer development?
Research Conclusion:
This study reveals that the metabolic enzyme HPD functions as a non-canonical RBP that promotes glycolytic flux, tumor growth, and chemoresistance in ovarian cancer by influencing the translation efficiency of mRNA. Proteomic technologies were employed to analyze the protein interaction network, providing robust support for elucidating the interaction mechanisms of HPD. This research not only redefines the classical theoretical framework of the tyrosine metabolic enzyme HPD, but also provides new insights for the precision treatment of ovarian cancer.
Study Design
## FAQ
1. Can we perform differential analysis based on qualitative proteomics?
- A: No. While qualitative proteomics identifies protein presence, the intensity values in its raw data are not suitable for direct differential analysis. These values are lacked the normalization and statistical rigor required for reliable comparisons of expression levels.
## Introduction to PRM Proteomics (AMEA haven’t launch)
- What is PRM Proteomics
PRM (Parallel Reaction Monitoring) Proteomics is a targeted protein quantitative technology based on high-resolution mass spectrometry. It realizes accurate quantification of target proteins by selectively monitoring precursor ions and fragment ions of specific peptides.
Relying on mature ultra-high-resolution mass spectrometry platform, Novogene launch a full-coverage and high-precision product-intelligent Parallel Reaction Monitoring (iPRM) proteomics, which is organically integrated the Thermo Orbitrap Astral ultra-high-resolution mass spectrometry platform and combined with an intelligent data processing system. It perfectly overcomes the limitation of traditional PRM (only targeting 30 proteins per experiment), the bottlenecks of data analysis, and the error of analysis, providing a new powerful tool for targeted proteomics verification.
* For any customer inquiries regarding PRM Proteomics, please reach out to the APM team to facilitate evaluation and pricing.
## Workflow of PRM Proteomics
Define the list of target proteins customers want to quantify
Identify target proteins/peptides
Select precursor ions of specific peptides for fragmentation in the collision cell
Scan the resulting fragment ions using the Astral mass analyzer
Quantify peptides (relative/absolute) based on fragment ion signal intensities, enabling specific analysis of target proteins/peptides in complex samples
Figure 15 The workflow of PRM Proteomics
Figure 16 The schematic diagram
## Sample Requirements and Guidelines
The sample collection and requirements for PRM proteomics are similar to quantitative proteomics. For detailed information, please refer to the 2.3 Sample Requirements and Guidelines in the quantitative proteomics section.
Acquisition Parameters in PRM Proteomics
Service
PRM Proteomics
Scan mode
DIA
Run time
8/15/24 min
MS platform
Thermo Orbitrap Astral
Searching software
Spectronaut
Database
Swissprot for human and mice sample, Uniprot, NCBI, etc.
SampleA pooled sample derived from more than three customer-provided samplesWhy?Assess the detectability of the target protein and establish the corresponding mass spectrometry parametersResultsThe detection results for the customer-specified target proteinSampleA pooled sample derived from more than three customer-provided samplesWhy?Assess the detectability of the target protein and establish the corresponding mass spectrometry parametersResultsThe detection results for the customer-specified target proteinData Preprocessing and Analysis Pre-test & Analysis
Sample
A pooled sample derived from more than three customer-provided samples
Why?
Assess the detectability of the target protein and establish the corresponding mass spectrometry parameters
Results
The detection results for the customer-specified target protein
Sample
A pooled sample derived from more than three customer-provided samples
Why?
Assess the detectability of the target protein and establish the corresponding mass spectrometry parameters
Results
The detection results for the customer-specified target protein
Test & Analysis
Sample
All samples provided by customers
Why?
Determination the expression level of targeted proteins
Results
The expression levels between groups
Key Advantages of PRM Proteomics in Novogene
Mass accuracy at the ppm level, enabling better background interference and false-positive exclusion compared to SRM/MRM, effectively improving detection limits and sensitivity in complex matrices
Full scan of fragment ions without the need for ion pair selection or collision energy optimization, simplifying method development
Antibody-free operation compared to conventional Western blot and ELISA, delivering more accurate and reproducible quantitative results
Wider linear dynamic range: extended to 5-6 orders of magnitude
Intelligent processing of PRM raw data, eliminating the manual workflows of traditional PRM targeted proteomics
Higher validation throughput: 300 proteins can be verified in a single iPRM experiment
Figure 17 Identified peptides/proteins by iPRM platform
Figure 18 The proportion of each component in the protein mixture of mouse, Escherichia coli, and Arabidopsis thaliana
Application for PRM Proteomics
Validation of large-scale screening data, such as target proteins identified through genomics/transcriptomics/quantitative proteomics, enabling their relative quantitative analysis
Complementary to Western blot and ELISA techniques, making protein validation simpler and providing more alternatives
Targeted screening of diagnostic biomarkers, verification and quantitative analysis of diagnostic markers
Case Study
Engineered hypermutation adapts cyanobacterial photosynthesis to combined high light and high temperature stress
Journal Publication: Nature communication
Impact Factor: 17.2
Date of Publication: 2023 March
Research Background:
Photosynthesis, the most critical biochemical process in Earth, sustains the biosphere through carbon fixation by plants and algae. Understanding and enhancing its efficiency and stability are of major scientific and technological significance. High-temperature and high-light stress (HTHL) significantly reduce photosynthetic productivity, leading to substantial economic losses in agriculture, forestry, and animal husbandry. Improving the thermotolerance and phototolerance of photosynthetic organisms is therefore a key research priority. Cyanobacteria, as model photosynthetic systems, offer valuable insights: enhancing their stress resilience and deciphering the underlying mechanisms can inform the optimization of other photosynthetic organisms. However, the complexity of stress-induced damage-affecting multiple targets through unclear mechanisms—hinders effective improvement via conventional metabolic or evolutionary engineering.
Research Conclusion:
Successfully established a highly efficient cyanobacterial mutagenesis system capable of screening HLHT-tolerant strains within two weeks.
The NC2 mutation is a key adaptive mutation that systematically optimizes photosynthetic efficiency and stability by upregulating shikimate kinase expression.
Overexpression of shikimate kinase is an effective strategy for optimizing photosynthesis, applicable to various cyanobacteria.
Metabolic remodeling induced by the NC2 mutation includes:
Enhanced cyclic electron flow and ATP synthesis;
Optimized carbon fixation and energy allocation;
Improved protein synthesis and antioxidant capacity.
This study provides a novel method for studying stress adaptation evolution in photosynthetic organisms and offers candidate targets for improving stress tolerance in crops and microorganisms.
Study Design
## FAQ
- Can we obtain the absolute expression level of proteins?
- A: Yes, absolute quantification is achievable. However, unlike relative quantification which compares protein levels between samples, absolute quantification requires a known amount of a reference standard for each protein (or prototypic peptide) to be measured. The most common and accurate approach uses synthetic, stable isotope-labeled peptides as internal standards, which are spiked into the sample prior to analysis.
- What is the recommended number of samples for PRM proteomics?
- A: The required sample size is determined by the number of experimental groups, sample category, and corresponding recommended biological replicates. For the minimum total sample size, mass-based proteome analysis generally requires at least 3 samples.
## Introduction to PTM Proteomics
- What is PTM Proteomics
PTM proteomics systematically characterizes the types, sites, and dynamics of protein post-translational modifications across the proteome. PTMs constitute core mechanisms of fine-tuned cellular regulation by:
Instantly modulating protein activity, localization, and interactions
Orchestrating critical processes: signal transduction, metabolic reprogramming, disease pathogenesis and others
Phosphoproteomics
The large-scale analysis of protein phosphorylation sites and a useful tool of defining signaling network regulation and dysregulation. Protein phosphorylation is one of the most common and important PTMs. This reversible mechanism occurs through protein kinases and consists of the addition of a phosphate group (PO4) to the polar group R of various amino acids (eg. Serine/S, threonine/T, or tyrosine/Y).
Figure 19 Schematic diagram of phosphorylation modification and functions
Acetylproteomics
Mapping the distribution, dynamics and regulatory functions of lysine acetylation (Kac) proteome-wide. Acetylation is added by acetyltransferases (HATs) and removed by deacetylases (HDACs), with dual functions of epigenetic regulation and metabolic regulation.
Figure 20 Schematic diagram of acetylation modification and functions
Ubiquitinomics
A study of identifying and quantifying ubiquitylated proteins and to map ubiquitylations at single amino acid. The attachment of ubiquitin to protein substrate (ubiquitination) is an important PTM for proteostasis and signal transduction. Ubiquitination is catalysed sequentially by ubiquitin activating enzyme (E1), ubiquitin-conjugating enzymes (E2) and ubiquitin-ligase enzymes (E3).
Figure 21 Schematic diagram of ubiquitination modification and functions
N/O-glycoproteomics
Glycosylation is one of the most intricate and variable post-translational modifications (PTMs), playing a pivotal role in various biological processes such as cell signalling, immune response, protein folding, and molecular recognition. The dynamic and diverse nature of glycosylation makes it an essential modification in cellular function and organismal development, as well as in disease progression. Glycoproteomics has emerged as a core field that enables the in-depth analysis of glycoproteins, providing valuable insights into the glycosylation sites and the underlying glycan structures. This is particularly important for understanding how changes in glycosylation patterns are linked to disease states, such as cancer, autoimmune disorders, and neurodegenerative diseases.
Figure 22 Depiction of the N-glycan core and each of the four N-glycan subclasses
Figure 23 O-glycans have eight canonical core structures. Some only differ by the linkage between two saccharides
Lactylproteomics (AMEA haven’t launch)
A field dedicated to characterizing the global dynamics and regulatory functions of lysine lactylation (Kla) across the proteome. Lactylation, referring to the covalent coupling of the lactyl group with lysine (K) residues, is a recently defined post-translational modification. This modification is formed by
lactate through non-enzymatic or enzymatic reactions (such as mediated by ACAT2), serving as the intersection of metabolic reprogramming and epigenetic regulation.
* For any customer inquiries regarding Lactylproteomics, please reach out to the APM team to facilitate evaluation and pricing.
Figure 24 Schematic diagram of lactylation modification and functions
## Workflow of PTM Proteomics
The standard proteomics workflow encompasses protein extraction, digestion, enrichment, desalting, instrumental analysis, and data processing. According to different modification, the suitable enrichment methods are be employed. Specific details can be referred to the following table.
TypeModification SitesEnrichmentPhosphorylationSer/Thr/Tyr(S/T/Y)TiO2AcetylationLys (K)Antibody-basedUbiquitinationLys (K)Antibody-basedO-glycosylationSer/Thr (S/T)Antibody-basedN-glycosylationAsn-X-Ser/Thr (X≠Pro)*HILICLactylationLys (K)Antibody-basedTypeModification SitesEnrichmentPhosphorylationSer/Thr/Tyr(S/T/Y)TiO2AcetylationLys (K)Antibody-basedUbiquitinationLys (K)Antibody-basedO-glycosylationSer/Thr (S/T)Antibody-basedN-glycosylationAsn-X-Ser/Thr (X≠Pro)*HILICLactylationLys (K)Antibody-basedAs each step - from sample preparation to mass spectrometry - can impact data quality and the validity of subsequent bioinformatic analysis, Novogene implements rigorous quality control and standardized protocols at every stage to ensure the generation of highly accurate and reliable data from the source.
Type
Modification Sites
Enrichment
Phosphorylation
Ser/Thr/Tyr(S/T/Y)
TiO2
Acetylation
Lys (K)
Antibody-based
Ubiquitination
Lys (K)
Antibody-based
O-glycosylation
Ser/Thr (S/T)
Antibody-based
N-glycosylation
Asn-X-Ser/Thr (X≠Pro)*
HILIC
Lactylation
Lys (K)
Antibody-based
Type
Modification Sites
Enrichment
Phosphorylation
Ser/Thr/Tyr(S/T/Y)
TiO2
Acetylation
Lys (K)
Antibody-based
Ubiquitination
Lys (K)
Antibody-based
O-glycosylation
Ser/Thr (S/T)
Antibody-based
N-glycosylation
Asn-X-Ser/Thr (X≠Pro)*
HILIC
Lactylation
Lys (K)
Antibody-based
- Note: * the labeled amino acid is asparagine (Asn).
Figure 25 The workflow of PTM proteomics
## Sample Requirements and Guidelines
The SG lab cannot process sample treatment for PTM proteomics services.
For more details about sample requirements and preparation method, please click the link: Novogene-AMEA-Sample-Submission-Guideline_Mass-Spectrometry-2025-03-V1.pdf.
Acquisition Parameters in PTM Proteomics
Service
Phosphoproteomics/Acetylproteomics/Ubiquitinomics/Lactylproteomics
N/O-glycoproteomics
Scan mode
DIA (data-independent acquisition)
DDA (data-dependent acquisition)
Run time
24 min
120 min
MS platform
Thermo Orbitrap Astral
Thermo Q ExactiveTM HF-X
Searching software
DIA-NN
pGlyco 3.0, pGlycoQuant
## Data Preprocessing and Analysis
Identification of PTM Sites
The process for determining modification sites without a database relies on targeted enrichment and mass shift analysis. The workflow is as follows:
Enrichment: After digestion and desalting, modified peptides are specifically isolated from the sample.
LC-MS/MS analysis: The enriched peptide pool is separated by liquid chromatography and analyzed by tandem mass spectrometry.
TypeMass shiftPhosphorylation79.966Ubiquitination114.043Acetylation42.011N/O-glycation203.079Lactylation72.021TypeMass shiftPhosphorylation79.966Ubiquitination114.043Acetylation42.011N/O-glycation203.079Lactylation72.021Site localization: The specific modification site is identified by detecting the characteristic mass-to-charge (m/z) shift in the fragment ions, which pinpoints the modified amino acid. Specific mass shift can be referred to the following table.
Type
Mass shift
Phosphorylation
79.966
Ubiquitination
114.043
Acetylation
42.011
N/O-glycation
203.079
Lactylation
72.021
Type
Mass shift
Phosphorylation
79.966
Ubiquitination
114.043
Acetylation
42.011
N/O-glycation
203.079
Lactylation
72.021
Figure 26 The diagram of modified peptides detection in LC-MSMS
Normalization of Proteomic and PTM Proteomic Data
Post-translational modifications (PTM) can dramatically alter the function of proteins and have important roles in disease and health as biomarkers or pharmaceutical targets. An important aspect of PTMs is the rate of site occupancy or PTM stoichiometry, which can provide biological information irrespective of the underlying protein abundance.
In proteomics experiments where modifications are studied using an enrichment step, it is important to decouple the changes in PTM site quantity from the changes in protein abundance in the original sample. This is achieved by performing input (pre-enrichment samples) normalization of PTM site quantity. Quantile normalization (peptide- modification sites intensity/ protein quantitation intensity) was suitable for PTM proteomic data.
It is recommended to analyze quantitative proteomics and PTM proteomics simultaneously from the same sample.
Figure 27 The workflow of normalization
## BI Analysis
Figure 28 Overview of the bioinformatics analysis workflow (PTM proteomics- Phosphoproteomics, Acetylproteomics, and Ubiquitinomics).
Figure 29 Overview of the bioinformatics analysis workflow (PTM proteomics- N/O-glycoproteomics).
Project Experience in Novogene
Figure 30 Identified modified sites with different PTMs (Deep DIA)
Figure 31 Identified modified peptides with different samples and peptide concentration
Key Advantages of PTM Proteomics in Novogene
In-depth analysis of PTMs, decoding "dark matter" of life regulation
Increased depth of site identification: phosphorylation site > 80,000, acetylation/ubiquitination site > 60,000, lactylation site > 20,000.
Improved accuracy of site identification: Class I sites ≥ 90%.
Multi-dimensional analysis and annotation
Precisely localize modification sites and quantify dynamic fluctuations.
Multi-dimensional functional decoding through the analysis of domains, kinase prediction, interaction networks, disease associations, etc.
Transform high-dimensional data into functional catalogues.
Figure 32 Proportion of class I sites (high-quality detected sites)
Figure 33 Characteristic analysis of identified proteins with PTM site (partial)
Application for PTM Proteomics
Regulation of protein function: PTMs precisely control protein activity, stability, localization, and interactions. This allows cells to dynamically fine-tune protein behavior in response to stimuli, regulating essential processes from signal transduction and metabolism to gene expression.
Enzyme regulation: PTMs directly regulate enzyme activity. For instance, phosphorylation can activate or inhibit catalytic function, thereby controlling key cellular signaling and metabolic pathways.
Targeted protein degradation: PTMs tag proteins for destruction. Ubiquitination, for example, marks damaged or unnecessary proteins for proteasomal degradation, facilitating their removal from the cell.
Cell signaling: PTMs are central to cellular communication. Modifications like phosphorylation and acetylation act as molecular switches that turn proteins "on" or "off," enabling cells to relay and respond to signals effectively.
Disease biomarkers: Aberrant PTM patterns are directly linked to diseases such as cancer and neurodegenerative disorders. Detecting these altered PTMs provides valuable biomarkers for improved diagnosis, prognosis, and drug target identification.
Drug development: Understanding PTMs enables the design of targeted therapies. Modifying specific PTMs can restore normal protein function and cellular processes, presenting promising new therapeutic strategies.
Customer Literature and Application Scenarios
No.
Title
Service
Application scenario
IF
DOI
1
Targeting TTK Inhibits Tumorigenesis of T-Cell Lymphoma Through Dephosphorylating p38α and Activating AMPK/mTOR Pathway
Phosphorylation
Oncology, Molecular
14.1
doi: 10.1002/advs.2024139
90
2
Protein phosphatase EYA1 regulates the dephosphorylation and turnover of BCL2L12 to promote glioma development
Phosphorylation
Oncology, Molecular
10
doi: 10.7150/ijbs.99619
3
EGFR TKIs suppress MUC1 glycosylation through the PI3K/AKT/SP1/C1GALT1 pathway to enhance TmMUC1 CAR-T efficacy in EGFR-mutant NSCLC
N/O-glycation
Oncology, Immunotherapy
10.6
doi: 10.1016/j.xcrm.2025.10
2199
4
Cancer-associated SPOP mutations enlarge nuclear size and facilitate nuclear envelope rupture upon farnesyltransferase inhibitor treatment
Ubiquitination
Cancer biology, Pharmacology
13.6
doi: 10.1172/JCI189048
5
A Stinkbug Salivary Protein Is Indispensable for Insect Feeding and Activates Plant Immunity
Acetylation
Botany, Immunity
6.3
doi: 10.1111/pce.15308
Case Study
Ketohexokinase-C regulates global protein acetylation to decrease carnitine palmitoyltransferase 1a-mediated fatty acid oxidation
Journal Publication: Journal of hepatology
Impact Factor: 25.7
Date of Publication: 2023 July
Research Background:
The consumption of sugar and a high-fat diet (HFD) promotes the development of obesity and metabolic dysfunction. Despite their well-known synergy, the mechanisms by which sugar worsens the outcomes associated with a HFD are largely elusive.
Research Conclusion:
Ketohexokinase-C (KHK-C)-induced acetylation is a novel mechanism by which dietary fructose augments lipogenesis and decreases fatty acid oxidation to promote the development of metabolic complications.
Study DesignStudy Design
Study Design
Personalized molecular signatures of insulin resistance and type 2 diabetes
Journal Publication: Cell
Impact Factor: 45.5
Date of Publication: 2025 July
Research Background:
Type 2 diabetes (T2D) is a highly heterogeneous disease, with insulin resistance (IR) being one of its core characteristics. It is primarily manifested as reduced sensitivity to insulin in tissues such as skeletal muscle, leading to impaired blood glucose regulation. As the disease progresses, patients face an increased risk of various complications, including cardiovascular diseases and nephropathy. Currently, there are over 500 million
cases worldwide, placing significant pressure on public health. However, due to substantial individual differences in insulin resistance and metabolism among patients, traditional diagnostic and treatment approaches face considerable challenges.
Mass spectrometry-based proteomics has become a powerful tool for elucidating regulatory mechanisms within the cellular proteome. Previous research utilizing proteomics and phosphoproteomics has identified MINDY1 as a regulator of insulin action, revealing how exercise improves insulin sensitivity through phosphorylation signaling. Nevertheless, the molecular mechanisms underlying insulin sensitivity and its variations among different individuals remain poorly understood.
Research Conclusion:
This study analyzed skeletal muscle samples from over 120 individuals with normal glucose tolerance and T2D, creating the most comprehensive and the world's first skeletal muscle proteomic and phosphoproteomic map encompassing both fasting and insulin-stimulated states. It systematically delineated the molecular characteristics of insulin resistance. Through a sophisticated cohort design that compared fasting versus insulin-stimulated states and healthy individuals versus those with T2D, this research overturned the traditional paradigm focused solely on post-insulin stimulation responses. It profoundly revealed personalized molecular features associated with insulin resistance and T2D. The combined use of a discovery cohort and a validation cohort, along with the verification of proteomic data using PRM targeted technology, also provides an excellent model for subsequent cohort studies.
Study Design
## FAQ
What can we get from PTM proteomics?
- A: PTM proteomics provides two primary types of information:
The Identity of PTMs: This includes the specific sites of modification (e.g., Serine 105) and the corresponding proteins that carry these sites.
The Relative Abundance of PTMs: This refers to the quantifiable changes in the modification levels at those specific sites across different samples or conditions.
- How do we perform the analyses in PTM proteomics?
- A: Our analysis hinges on identifying statistically significant changes in PTM levels at specific sites. We then interpret these "differential modified sites" and their carrier proteins through functional enrichment to derive biological insights.
- What is the recommended number of samples for PTM proteomics?
- A: The required sample size is determined by the number of experimental groups, sample category, and corresponding recommended biological replicates. For the minimum total sample size, mass-based proteome analysis generally requires at least 3 samples.
## Multi-omics Analysis
Proteomics can be integrated with transcriptomics, PTM proteomic, and metabolomics for correlation analysis.
For demo reports or related details, please refer to the AMEA WeDrive folder https://drive.weixin.qq.com/s?k=AJgAAQcaAAwtPXtifq or contact the APM team.
Why should We Include Proteomics in Multi‑omics Research?
OmicsWhat it tells us?What can still be missing without proteomicsRecommended reference(s)TranscriptomicsMeasures the levels of all messenger RNA (mRNA) in a cell, revealing which genes are being actively transcribed. It reflects the potential for gene expression.Protein Abundance: mRNA levels are poor predictors of actual protein levels (due to translational control and protein degradation).Protein Function: It cannot determine if the corresponding proteins are active, localized correctly, or form functional complexes.Post-Translational Modifications (PTMs): It completely misses key regulatory mechanisms that control protein activity.doi: 10.1093/bib/bbw114OmicsWhat it tells us?What can still be missing without proteomicsRecommended reference(s)TranscriptomicsMeasures the levels of all messenger RNA (mRNA) in a cell, revealing which genes are being actively transcribed. It reflects the potential for gene expression.Protein Abundance: mRNA levels are poor predictors of actual protein levels (due to translational control and protein degradation).Protein Function: It cannot determine if the corresponding proteins are active, localized correctly, or form functional complexes.Post-Translational Modifications (PTMs): It completely misses key regulatory mechanisms that control protein activity.doi: 10.1093/bib/bbw114Proteomics serves as a central pillar in multi-omics studies, integrating genomic, transcriptomic, and epigenomic data to bridge the gap between genetic blueprint and biological function. By quantifying protein expression, post-translational modifications, and interactions, proteomics provides a functional information of cellular activity that mRNA levels alone cannot capture. Yet without proteomics, the picture remains fundamentally incomplete. Proteins are the primary executors of biological processes and the targets of most drugs; their abundances and states directly determine phenotype. While other omics layers suggest potential mechanisms, proteomics delivers direct evidence of functional regulation, transforming correlative multi-omics associations into causal mechanistic insights.
Omics
What it tells us?
What can still be missing without proteomics
Recommended reference(s)
Transcriptomics
Measures the levels of all messenger RNA (mRNA) in a cell, revealing which genes are being actively transcribed. It reflects the potential for gene expression.
Protein Abundance: mRNA levels are poor predictors of actual protein levels (due to translational control and protein degradation).
Protein Function: It cannot determine if the corresponding proteins are active, localized correctly, or form functional complexes.
Post-Translational Modifications (PTMs): It completely misses key regulatory mechanisms that control protein activity.
doi: 10.1093/bib/bbw114
Omics
What it tells us?
What can still be missing without proteomics
Recommended reference(s)
Transcriptomics
Measures the levels of all messenger RNA (mRNA) in a cell, revealing which genes are being actively transcribed. It reflects the potential for gene expression.
Protein Abundance: mRNA levels are poor predictors of actual protein levels (due to translational control and protein degradation).
Protein Function: It cannot determine if the corresponding proteins are active, localized correctly, or form functional complexes.
Post-Translational Modifications (PTMs): It completely misses key regulatory mechanisms that control protein activity.
doi: 10.1093/bib/bbw114
PTM
proteomics
Specifically identifies and analyses post-translational modifications of proteins, such as phosphorylation, acetylation, and ubiquitination. It directly reveals crucial information about protein functional activity and regulatory status.
Total Protein Abundance: It focuses on the modified forms and may lack the global context of the total protein's abundance.
Biological Context: The significance of a modification event often requires integration with total protein levels and pathway context for full interpretation.
Non-PTM Regulation: It does not capture regulation that occurs at the level of transcription, translation, or protein degradation rates.
doi: 10.4155/bio.14.296
Metabolomics
Systematically measures the composition and concentration of all small molecule metabolites (e.g., sugars, amino acids, lipids) in a cell or organism. It is the closest readout of the phenotype, reflecting the final output of cellular physiological states.
Direct Regulatory Mechanism: It shows "what is happening" but not "why it is happening." It cannot identify which enzymes (proteins) are responsible for the metabolite changes.
Pathway Bottlenecks: It cannot distinguish if a metabolic flux change is due to enzyme abundance, activity, or allosteric regulation.
Upstream Signalling: It cannot trace back the signalling events (often mediated by proteins and their PTMs) that led to the metabolic changes.
doi: 10.1097/MCC.00000000
00000966
Parallel Research Framework of Multi-omics Research
Figure 34 Parallel research framework of multi-omics research
Demo Results for Proteomics - Transcriptomics and Proteomics – Metabolomics Integration Analysis
Please see the details in demo report: https://drive.weixin.qq.com/s?k=AJgAAQcaAAwtPXtifq
## Appendix
Supplementary Knowledge on Protein Research
Basic Information of Protein
Protein primary structure
Primary Structure describes the unique order in which amino acids are linked together to form a protein. All amino acids have the alpha carbon bonded to a hydrogen atom, a carboxyl group, and an amino group. The "R" group varies among amino acids and determines the differences between these protein monomers. The amino acid sequence of a protein is determined by the information found in the cellular genetic code. The order of amino acids in a polypeptide chain is unique and specific to a particular protein. Altering a single amino acid causes a gene mutation, which most often results in a non-functioning protein.
Protein mass spectrometry analysis determines the sequence of peptide segments and thereby identifies proteins. Refer to https://www.nature.com/scitable/topicpage/protein-structure-14122136/)
Figure 35 The relationship between amino acid side chains and protein conformation
Hydrophilicity and Hydrophobicity
The hydrophobicity of amino acids reflects the folding of proteins, with hydrophobic regions often appearing in potential transmembrane segments. It plays a crucial role in maintaining the tertiary structure of proteins, such as stabilizing biological membranes. Hydropathicity/hydrophobicity profiles can provide references for identifying transmembrane regions in proteins.
Isoelectric Point
The isoelectric point (pI) of a protein refers to the pH at which the protein carries a net charge of zero under specific conditions. Determining the isoelectric point of a protein holds significant importance in the following aspects: determining the charge state of the protein, optimization of protein purification processes, predicting protein structure and function, and studying protein stability and aggregation propensity.
Western Blot
Western blotting (WB) is a powerful technique that allows you to positively detect your proteins, estimate quantities, and determine their molecular weights. All from a starting mixture of proteins extracted from cells or tissues.
It’s a useful tool for validation after LC-MSMS.
Figure 36 The workflow of WB
IP/Co-IP
Immunoprecipitation (IP) is a technique used to enrich specific proteins from heterogeneous cellular or tissue extracts using target-specific antibodies. Co-immunoprecipitation (Co-IP) refers to the precipitation of intact protein complexes. Both IP and co-IP are widely utilized techniques for identifying protein-protein interactions and novel components within protein complexes.
Regularly, the detection of IP/Co-IP samples is western blot, however, the limitation of this method is that only one protein in once detection. Based on LC-MSMS detection (quantitative/qualitative proteomics, sample type: beads, gel, and so on) could achieve the high-throughput detection.
Refer to https://www.cellsignal.com/learn-and-support/videos-and-webinars/co-immunoprecipitation-bait-prey
Figure 37 The diagram of beads-proteins compound
Figure 38 A typical immunoprecipitation procedure, in which the target protein (in red) is enriched and separated from other proteins (in blue) in the lysate. The rightmost box represents Western blot analysis. Lane labels: M, marker; I, input lysate; B, binding fraction (immunoprecipitation); U, unbound portion.
Elisa
The ELISA technique relies on the interaction between the antigen (i.e., the target protein) and a primary antibody directed against the target antigen. The presence of the antigen is confirmed through the catalysis of an added substrate by an enzyme-conjugated antibody.
In ELISA, a liquid sample with specific binding properties is added to a fixed solid phase within a reaction chamber or microplate. Different liquid reagents are then incubated sequentially, leading to an optical change in the final liquid (e.g., color development from an enzymatic reaction product). The results can be detected qualitatively by visual inspection or quantitatively using readings from a photometer or spectrophotometer.
It’s useful tool for detection and validation of protein biomarkers.
Refer to Principle of ELISA (Enzyme-linked Immunosorbent Assay) Test | Cell Signaling Technology
Flow Cytometry
Flow cytometry is an integrated platform that combines electronics, fluidics, optics, software, and laser technologies to measure the characteristics of individual cells or particles suspended in a flowing stream. This technique analyzes thousands of targets per second on a cell-by-cell basis, using fluorescence and light scattering to determine their phenotype. The information gathered can then be utilized to individually sort or separate specific subpopulations of cells within a specialized cell sorter instrument.
Flow cytometry could explore and validate bioinformation about protein expression, signaling transduction, and so on.
Note
All services are for Research Use Only. Not for Clinical Diagnostic Use.
Reference
Reference for Basic Concepts in Proteomics
Ardito F; Giuliani M; Perrone D; et al. The crucial role of protein phosphorylation in cell signaling and its use as targeted therapy. Int J Mol Med, 2017, 40(2): 271-280.
Chen H; Zhang L; Liu M; et al. Multi-Omics Research on Angina Pectoris: A Novel Perspective. Aging Disease, 2024.
Helms A; Brodbelt JS. Mass Spectrometry Strategies for O-Glycoproteomics. Cells, 2024, 13(5): 394.
Hesami M; Alizadeh M; Jones AMP; et al. Machine learning: its challenges and opportunities in plant system biology. Appl Microbial Biotechnology, 2022,106(9-10): 3507-3530.
Kitata RB; Yang JC; Chen YJ. Advances in data-independent acquisition mass spectrometry towards comprehensive digital proteome landscape. Mass Spectrom Rev, 2023, 42(6): 2324-2348.
Liu M; Guo L; Fu Y; et al. Bacterial protein acetylation and its role in cellular physiology and metabolic regulation. Biotechnol Adv, 2021, 53: 107842.
Liu J; Li W; Wang L; et al. Multi-omics technology and its applications to life sciences: a review. Chinese Journal of Biotechnology, 2022, 38(10): 3581-3593.
Robinson JM; Hodgson R; Krauss SL; et al. Opportunities and challenges for microbiomics in ecosystem restoration. Trends Ecol Evol, 2023, 38(12): 1189-1202.
Shen B; Yi X; Sun Y; et. Al. Proteomic and Metabolomic Characterization of COVID-19 Patient Sera. Cell, 2020, 182(1): 59-72.
Swatek KN, Komander D. Ubiquitin modifications. Cell Res. 2016, 26(4):399-422.
Timp W, Timp G. Beyond mass spectrometry, the next step in proteomics. Science Advance, 2020, 6(2): eaax8978.
Xu Y, Zhang L, Shang D; et al. Lactylation: From Molecular Insights to Disease Relevance. Biomolecules. 2025, 15(6): 810.
Reference for Quantitative proteomics
Ashburner M; Ball C A; Blake J A; et al. Gene ontology: tool for the unification of biology. The Gene Ontology Consortium. Nature Genetics, 2000, 25(1): 25-29.
Finn RD; Attwood TK; et al. InterPro in 2017 - beyond protein family and domain annotations. Nucleic Acids Research, Jan 2017.
Franceschini A; Szklarczyk D; Frankild S; et al. STRING V9.1: Protein-Protein Interaction Networks, with Increased Coverage and Integration. Nucleic Acids Research, 2012, 41(1).
Huang D W; Sherman B T; Lempicki R A. Bioinformatics enrichment tools: paths toward the comprehensive functional analysis of large gene lists. Nucleic Acids Research, 2009, 37(1): 1-13.
Jin J; Zhang H; Kong L; et al. PlantTFDB 3.0: a portal for the functional and evolutionary study of plant transcription factors. Nucleic acids research, 2013, 42(1): 1182-1187.
Kanehisa M; Goto S; Hattori M; et al. From genomics to chemical genomics: new developments in KEGG. Nucleic Acids Research, 2006, 34: 354-357.
Kanehisa M; Goto S; Kawashima S; et al. The KEGG resource for deciphering the genome. Nucleic Acids Research, 2004, 32: 277-280.
Liu G; Fu T; Han Y; et al. Probing Protein-Protein Interactions with Label-Free Mass Spectrometry Quantification in Combination with Affinity Purification by Spin-Tip Affinity Columns. Anal Chem. 2020;92(5): 3913-3922.
Muntel J; Xuan Y; Berger S T; et al. Advancing Urinary Protein Biomarker Discovery by Data-independent Acquisition on a Quadrupole-Orbitrap Mass Spectrometer. Journal of Proteome Research, 2015, 14(11): 4752.
Subramanian A; Tamayo P; Mootha V K; et al. Gene set enrichment analysis: a knowledge-based approach for interpreting genome-wide expression profiles. Proc Natl Acad Sci U S A. 2005.
Tatusov R L; Fedorova N D; Jackson J D; et al. The COG database: an updated version includes eukaryotes. BMC bioinformatics, 2003, 4(1): 41.
Wu J; An Y; Pu H; et al. Enrichment of serum low-molecular-weight proteins using C18 absorbent under urea/dithiothreitol denatured environment. Anal Biochem 2010, 398(1): 34-44.
Wu J.; Xie X.; Liu Y.; et al. Identification and confirmation of differentially expressed fucosylated glycoproteins in the serum of ovarian cancer patients using a lectin array and LC-MS/MS. Journal of Proteome Research. 2012, 11(9): 4541-4552.
Zhang H M; Chen H; Liu W; et al. AnimalTFDB: a comprehensive animal transcription factor database. Nucleic acids research, 2011, 40(1): 144-149.
Reference for Qualitative Proteomics
Ashburner M; Ball C A; Blake J A; et al. Gene ontology: tool for the unification of biology. The Gene Ontology Consortium. Nature Genetics, 2000, 25(1): 25-29.
Finn RD; Attwood TK; et al. InterPro in 2017 - beyond protein family and domain annotations. Nucleic Acids Research, Jan 2017.
Jin J; Zhang H; Kong L; et al. PlantTFDB 3.0: a portal for the functional and evolutionary study of plant transcription factors. Nucleic acids research, 2013, 42(1): 1182-1187.
Jones P; Binns D; Chang H Y; et al. InterProScan 5: genome-scale protein function classification[J]. Bioinformatics, 2014, 30(9): 1236-1240.
Kanehisa M; Goto S; Hattori M; et al. From genomics to chemical genomics: new developments in KEGG. Nucleic Acids Research, 2006, 34: 354-357.
Kanehisa M; Goto S; Kawashima S; et al. The KEGG resource for deciphering the genome. Nucleic Acids Research, 2004, 32: 277-280.
Muntel J; Xuan Y; Berger S T; et al. Advancing Urinary Protein Biomarker Discovery by Data-independent Acquisition on a Quadrupole-Orbitrap Mass Spectrometer. Journal of Proteome Research, 2015, 14(11): 4752.
Tatusov R L; Fedorova N D; Jackson J D; et al. The COG database: an updated version includes eukaryotes. BMC bioinformatics, 2003, 4(1): 41.
Wu J; An Y; Pu H; et al. Enrichment of serum low-molecular-weight proteins using C18 absorbent under urea/dithiothreitol denatured environment. Anal Biochem 2010, 398(1): 34-44.
Wu J.; Xie X.; Liu Y.; et al. Identification and confirmation of differentially expressed fucosylated glycoproteins in the serum of ovarian cancer patients using a lectin array and LC-MS/MS. Journal of Proteome Research. 2012, 11(9): 4541-4552.
Zhang H M; Chen H; Liu W; et al. AnimalTFDB: a comprehensive animal transcription factor database. Nucleic acids research, 2011, 40(1): 144-149.
Zhang H; Liu T; Zhang Z; et al. Integrated Proteogenomic Characterization of Human High-Grade Serous Ovarian Cancer. Cell, 2016.
Reference for PRM Proteomics
MacLean, B.; Tomazela, D. M.; Abbatiello, S. E.; et al. Effect of collision energy optimization on the measurement of peptides by selected reaction monitoring (SRM) mass spectrometry. Anal. Chem. 2010, 82 (24).
Peterson, A. C.; Russell, J. D.; Bailey, D. J.; et al. Parallel reaction monitoring for high resolution and high mass accuracy quantitative, targeted proteomics. Mol. Cell Proteomics 2012, 11 (11): 1475-1488.
Carrera, M.; Gallardo, J. M.; Pascual, S.; et a, I. Protein biomarker discovery and fast monitoring for the identification and detection of Anisakids by parallel reaction monitoring (PRM) mass spectrometry. Journal of Proteomics 2016, 142: 130-113.
Serrano, L. R.; Peters-Clarke, T. M.; Arrey, T. N.; et al. The one hour human proteome. Mol. Cell Proteomics 2024, 23 (5).
Guzman, U. H.; Martinez-Val, A.; Ye, Z.; Damoc, E.; et al. Ultra-fast label-free quantification and comprehensive proteome coverage with narrow-window data-independent acquisition. Nat. Biotechnol. 2024.
Zeng, W.; Bateman, K. P. Quantitative LC-MS/MS. 1. impact of points across a peak on the accuracy and precision of peak area measurements. J. Am. Soc. Mass Spectrom. 2023, 34 (6).
MacLean, B.; Tomazela, D. M.; Shulman, N.; et al. Skyline: an open source document editor for creating and analyzing targeted proteomics experiments. Bioinformatics 2010, 26 (7): 966-968.
Demichev, V.; Messner, C. B.; Vernardis, S. I.; et al. DIA-NN: neural networks and interference correction enable deep proteome coverage in high throughput. Nat. Methods 2019, 17 (1): 41-44.
Cox, J.; Neuhauser, N.; Michalski, A.; et al. Andromeda: a peptide search engine integrated into the MaxQuant environment. J. Proteome Res. 2011, 10: 1794-1805.
Lesur, A.; Schmit, P.-O.; Bernardin, F.; et al. Highly multiplexed targeted proteomics acquisition on a TIMS-QTOF. Anal. Chem. 2020, 93 (3): 1383-1392.
Rappsilber, J.; Ishihama, Y.; Mann, M. Stop and go extraction tips for matrix-assisted laser desorption/ionization, nanoelectrospray, and LC/MS sample pretreatment in proteomics. Anal. Chem. 2003, 75: 663-670.
Chambers, M. C.; Maclean, B.; Burke, R.; et al. A cross-platform toolkit for mass spectrometry and proteomics. Nat. Biotechnol. 2012, 30 (10): 918-920.
Reference for PTM Proteomics
Crooks GE; Hon G, Chandonia JM; Brenner SE. (2004). WebLogo: A sequence logo generator, Genome Research, 14: 1188-1190.
FranceschiniA; SzklarczykD; FrankildS; et al. STRINGV9.1: Protein-Protein Interaction Networks, with Increased Coverage and Integration. Nucleic Acids Research, 2012, 41 (1).
Franceschini, A.; Szklarczyk, D.; Frankild, S.; et al. (2013). STRING v9.1: protein-protein interaction networks, with increased coverage and integration. Nucleic Acids Research: 808-815.
Huang da, W.; B.T. Sherman; R.A. Lempicki. (2009). Bioinformatics enrichment tools: paths toward the comprehensive functional analysis of large gene lists. Nucleic Acids Res 37: 1-13.
Jones P; Binns D; Chang HY; et al. InterProScan 5: genome-scale protein function classification. Bioinformatics, 2014, 30 (9): 1236-1240.
Jones, P.; Binns, D.; Chang, H.; et al. (2014). InterProScan 5: genome-scale protein function classification. Bioinformatics, 30(9): 1236-1240.
Miller, M. L.; Jensen, L. J.; Diella, F.; et al. (2008). Linear Motif Atlas for Phosphorylation-Dependent Signaling. Science Signaling, 1 (35).
Wagih O; Sugiyama N; Ishihama Y; et al. (2016). Uncovering Phosphorylation-Based Specificities through Functional Interaction Networks. Molecular & Cellular Proteomics, 15(1): 236-245.
Novogene Product Manual
Pre-made Library Sequencing
AMEA 2026.03
(This manual is for AMEA use only. Anyone shall not display or disseminate to others.
If you have any questions about the products, please consult APM team)
Product Manual Revisions
Subject
Novogene Product Manual – Pre-made Library Sequencing
Revision Number
2026 V1.0
Issue Date
March 2026
Prepared by
Yuxuan Luo
Reviewed by
Yan Liang
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Pg 4 – Add sample requirement of NovaSeq X Plus
Pg 7-12 – Adjust the FAQ related to NovaSeq X Plus, Hiseq X Pg 13-14 – Add Turn Around Time of different platforms
Pg 21 – Add custom sequence primer requirement of NovaSeq X Plus
Tianran Shi
May 2023
2023 V2.0
Delete sample requirement, FAQ and TAT about Hiseq X
Pg 4 – Add sample requirement of NovaSeq X Plus partial lane sequence
Pg 5 – Update the data amount and volume sample requirement of NovaSeq6000 PE250, PE50, and SE50
Pg 15 – Update the library size according to the library QC criteria Pg 15 – Add PhiX suggestion on more library types
Pg 21– Add notification about custom primer on NovaSeq X plus flowcell sequence
Tianran Shi
Sep 2023
2024 V1.0
Pg 3 – NGS Sequencing Platform Overview
Pg 5-7 – Add library requirement of NovaSeq X Plus 25B and DNBSEQ T7 PE150 Pg 6 – Delete sample requirement of NovaSeq6000 PE50 partial lane sequencing Pg 7 – FAQ3: Change requirement about TruSeq library
Pg 10 – Update the FAQ11 about the requirement of DNBSEQ T7 PE150 platform Pg 11 – Add FAQ12 and FAQ 13 about DNBSEQ T7 PE150 platform
Pg 16 – Update the PhiX recommendation of NovaSeq6000 and NovaSeq X Plus
Tianran Shi
Feb 2024
2024 V2.0
Pg 6 – For lane sequencing, the data output we promised comprises both determined and undetermined data
Pg 9 – Update FAQ5 about index base balance percentage requirement
Pg 11 – Update FAQ11 about compatible Illumina library types on DNBSEQ T7, delete cyclization fee of illumina library sequenced on DNBSEQ T7 PE150
Pg 13 – Add FAQ14 about BGI Stereo-seq library
Pg 28 – Update the requirement for custom sequence primer for NovaSeq X plus
Tianran Shi
Mar 2024
2024 V3.0
The modifications in this version are highlighted in the manual. Pg 4 – Add on MGI DNBseq T7 platform
Pg 8 – Add instructions on index selection in Pooling FAQ 1.
Pg10 – Add instructions about data output for customized configuration settings in Sequencing FAQ 1.
Pg 11 – Modifications on data output FAQ 1: If all the libraries on the same lane pass library QC, we can guarantee the total data output of a lane, we don’t guarantee the data output for each library.
Pg 14 – Add special library types that cannot be sequenced on the T7 platform in Special Library Types FAQ 1.
Pg 16 – Update special library types FAQ 5 about 10x single cell3’/5’ gene expression sequencing on T7. Add PhiX recommendation for 10x sc-multiome ATAC library.
Pg 18-19 – Update turnaround time FAQ 2.
Pg 21 – Add instructions on PhiX recommendation when pooling multiple library types. Pg 28 – Update we cannot guarantee data output when sequencing on Novaseq X plus
platform with customized primers.
Yuxuan Luo
June 2024
2024 V4.0
The modifications in this version are highlighted in the manual. Pg 4 – Update the data output of Novaseq X plus 10B.
Pg 4 – Update the sequencing configuration for 500 cycles kit.
Pg 7 –Modified the types of libraries that can be sequenced with PE50.
Pg 8 – Modifications on the required sample volume of Illumina linear libraries for sequencing on the DNBSEQ-T7 PE150 platform.
Pg 13 – Specify the conditions to guarantee the quantity of data output.
Pg 19 –Add recommendations for sequencing FFPE Stereo-seq transcriptomics libraries. Pg 21– Add sequencing guidelines for 10x Visium HD Library.
Yuxuan Luo
Aug 2024
2024 V5.0
The modifications in this version are highlighted in the manual.
Pg 5-6 – Updated data output and conditions for guaranteed data output on the DNBSEQ-T7 platform.
Yuxuan Luo
Oct 2024
Pg 10 – Updated acceptable library types and sample volumes for the DNBSEQ-T7.
Pg 11-12 – Added clarification regarding the inaccurate quantification of single-stranded libraries.
Pg 17-19 – Added library types that can be sequenced on the DNBSEQ-T7 PE150 and updated sequencing-related considerations.
Pg 27 – Updated PE150 library size ranges.
2026 V1.0
All the modifications in this version are highlighted in the manual.
Pg 5 – Updated the T7 PE150 data output information; added information on the T7 150 cycles chip.
Pg 6&9 – Updated detailed information on library types suitable for T7 PE100 and PE75, as well as data output.
Pg 11-12 – Added UMI-related instructions.
Pg 16 – Added explanations regarding libraries with unbalanced base composition on the T7 platform and index number requirements.
Pg 18 – Added detailed instructions for sequencing MGI adapter libraries.
Pg 20 – Added detailed explanations for the C4 and Stereo-seq library types.
Pg 22-23 – Added instructions for lane sequencing with special index configuration settings for 10x ATAC libraries.
Pg 26 – Updated the library size requirements for PE150.
Pg 27-29 – Updated suggestions for updating library PhiX Spike-in Ratio
Pg 36 – The procurement cycle forcustomized primer replacement reagents has been extended.
Yuxuan Luo
March 2026
Contents
NGS Sequencing Platform Overview5
Pre-made Library Requirements7
## FAQ10
Library Size26
Applications26
PhiX Suggestion27
Adapter Information27
Index Orientation33
Customer-supplied Sequencing Primer Requirements35
NGS Sequencing Platform Overview
Platform
NovoSeq X Plus
NovaSeq 6000
MGI DNBSEQ T7
Lab
China (Beijing
lab), Japan, Singapore
China, Japan, Singapore
China
Strategy
PE150
500 Cycle
PE50
SE50
PE150
PE100***
PE75***
Chip
10B
25B
SP
——
Flowcell/run
2
4
Lanes/ FC
8
2
1
Output/lane*
375Gb**
1000Gb***
400M reads
——
1740Gb ****
Depends on Lib type
****
Depends on Lib type
****
Output/FC*
3000Gb**
8000Gb***
800M reads
1740Gb ****
Depends on Lib type
****
Depends on Lib type
****
Configuration
151+10+10+151
256+8+8+256
50+8+16+50
51+8
150+10+10+150
****
Running time
～24h
～48h
～38h
～13h
～24h
——
Q30
>85%
——
Kit Version
——
V1.5
V3.0
——
Application
Premade library lane sequencing; most applications
Premade library lane sequencing (JP); most applications
Amplicon, PCR product, PML
10x ATAC
library only; PML FC
sequencing
PML FC
sequencing
WGS,
mRNA, etc
MGI C4 single cell library
Stereo seq
- Note:
*The data output is based on a balanced library and library passed library QC.
**10B PML guarantees a data output of 375 Gb per lane, subject to the following conditions:
Base-balanced library, with each lane having≥5 indexes, and all library QC in the PML graded as pass.
The theoretical data output of >375 Gb includes index, PhiX data, demultiplexed data, and data that cannot be multiplexed.
Do note: Tianjin lab will not offer 10B sequencing services any more. Samples requiring 10B sequencing in mainland China must be submitted to the Beijing lab.
***25B PML guarantees a data output of 1Tb per lane, subject to the following conditions:
Base-balanced library, with each lane having ≥5 indexes, and all library QC in the PML graded as pass.
The theoretical data output of >1Tb includes index, PhiX data, demultiplexed data, and data that cannot be multiplexed.
**** DNBseq T7 PE150 guarantees a data output of 1740 Gb per lane, subject to the following conditions:
The data output is based on a balanced library and library passed library QC, and the maximum-to-minimum insert fragment size difference should be less than 100 bp. All libraries in the same lane must be QC pass libraries. If there are any QC failed libraries, the output is not guaranteed.
FFPE library samples are not guaranteed for output (official standard).
**** DNBseq PE100 sequencing is only suitable for MGI C4 single-cell library sequencing, and experience data output is around 4400M reads.
Do note: We can currently guarantee the output for C4 libraries, provided that the data volume of the Oligo library does not exceed 500M reads when pooled with the cDNA library.
**** DNBseq PE75 sequencing is only suitable for Stereo-seq library sequencing, and depending on the different library prep kits (Stereo-seq FFPE/Stereo-seq FF V1.3), the expected output varies, Stereo-seq fresh frozen: 4000M reads, Stereo-seq FFPE: 5000M reads. If the library was performed with Stereo-seq FF V1.2 kit, the sequencing need to be arranged on DNBseq PE100.
Do note: the output for Stereo-seq libraries cannot be guaranteed at this point. Please check with customer about the library type and kit version.
Pre-made Library Sequencing
With our world-leading capacity Illumina platform, we are able to provide pre-made library sequencing services at highly competitive and cost-effective prices.
Pre-made Library Requirements
Platform
Lane
Data Amount (Gb data)
Volume
Concentration
Configuration (Default)
NovaSeq X Plus 10B PE150
1 FC=8 lanes
375 G/lane 3T/FC
Lane sequencing* (375 Gb data per lane)
≥ 70 μL/lane (add 70 µL for
each additional lane)
≥ 2 ng/μL, quantified by Qubit® 2.0 (Life Technologies)
or
≥ 2 nmol/L quantified by
qPCR
151+10+10+151;
(10+10 is dual index, 151 is read length)
NovaSeq X Plus 25B PE150
1 FC=8 lanes
1,000 G/lane 8.0T/FC
Lane sequencing* (1,000 Gb data per lane)
≥ 130 μL/lane (add 130 µL
for each additional lane)
NovaSeq X Plus PE150
Partial Lane
X < 30 G
≥ 15 µL
30 G ≤ X < 100 G
≥ 30 µL
100 G ≤ X < 375 G
≥ 70 µL
* For lane sequencing of NovaSeq X plus platform, please refer to the above NGS Sequencing Platform Overview- ‘Note’ information.
Platform
Lane
Data Amount * (Mb reads)
Volume
Concentration
Configuration (Default)
NovaSeq6000 SP 500 Cycle
1 FC=2
lanes;
400 M pair reads /lane
X < 30 M reads
≥ 15 µL
≥ 2 ng/μL, quantified by Qubit® 2.0 (Life Technologies) or
≥ 2 nmol/L quantified by qPCR
256+8+8+256;
(8+8 is dual index, 256 is read length)
30 M ≤ X < 100 M reads
≥ 25 µL
100 M ≤ X < 400 M reads
≥ 50 µL
Lane sequencing
(400 M pair reads per lane)
≥ 70 µL/lane (add 70 µL for each additional lane)
NovaSeq6000 SP SE50
1 FC=2
lanes
1 FC=2 lanes
Flowcell sequencing (800 M pair reads per flowcell)
≥ 140 µL/flowcell
51+8
(8 is single index, 51 is read length)
NovaSeq6000 SP PE50
Accept flowcell sequencing only,
don’t accept partial lane sequencing.
Primarily used for flowcell sequencing of 10x sc-ATAC libraries and other libraries suitable for PE50 flowcell sequencing.
Default configuration is 50+8+16+50, if customer uses multiome ATAC kit, please remark the kit and the sequencing
configuration 50+8+24+50 to the project manager.
- Note:
* For lane/FC sequencing, if all the libraries in the lane/ FC passed Novogene’s QC, the total data output we promised comprises both demultiplexed data, and data that cannot be multiplexed. Novogene only promises the data output per lane/ FC, instead of output for each library.
Platform
Library Type
Lane
Data Amount (Gb data)
Volume
Concentration
Configuration (Default)
DNB T7 PE150
Illumina/MGI Library
FC=lane; 1740Gb/ lane
X < 50 G reads
≥ 40 µL
≥ 2.5 ng/μL, quantified by Qubit® 2.0 (Life Technologies)
or
≥ 12 nmol/L quantified by qPCR
150+10+10+1
50
50 G ≤ X < 200 G
reads
≥ 60 µL
200 G ≤ X
≥ 80 µL
Lane sequencing
≥ 80 µL/lane (add 80 µL
for each additional lane)
Single cell C4/
DNB T7
Stereo-seq
FC=lane;
PE100
FF/Stereo-seq FF V1.2
Data output varies depending on Library type
For more details, please refer to Special Library Types FAQ4, for sample requirements (volume and concentration, please come to APM)
DNB T7 PE75
Stereo-seq
FFPE/Stereo-seq FF V1.3
## FAQ
Sample Preparation
What information should you check with client about premade library project? A: Please check the following information with client about their premade library:
Library prep kit (protocol) / Library type
Sequence of adapter (P5/P7 oligo; read1/read2 sequence primer; i5/i7 index)
Single index/ Dual index/ PE adapter without index
UMI/barcode
Customized sequence primer
Data amount
PhiX percentage (only add PhiX when doing lane/flowcell sequencing)
- Can we accept the samples that do not complete the library prep steps, and then continue to build the library for the customer?
- A: Sorry, we can’t. The library must have a complete structure.
- Can we offer purification for premade library? If the concentration is high, can the volume be lower than 15µL?
- A: We don’t offer purification for premade library. For premade libraries with high concentration, the volume could be decreased relatively, but the minimum standard of volume is supposed to be 15 µL. If the volume is lower than 15 µL, we suggest customer dilute the library on their own.
- What is the corresponding relationship between index1/2 and i5/i7 index?
- A: In Illumina sequencing platform, we generally call index (i5) at P5 end as index 2 and index (i7) at P7 end as index 1.
- Can we accept single-stranded libraries?
- A: Our current quantification process is designed for double-stranded libraries, so single-stranded libraries cannot be accurately quantified. Data yield for single-stranded libraries is limited, typically reaching only about half of the target amount. If the client still wants to proceed with sequencing, they must accept this risk. We do not guarantee output, and the charges will be based on the data volume ordered by the client. Only the Tianjin laboratory accepts single-stranded libraries.
About UMI sequence,
- What is the role of UMIs?
Removing PCR duplicates
UMIs allow reads originating from the same original molecule to be identified, so PCR duplicates can be collapsed into a single molecule, preventing artificial inflation of read counts.
Improving quantification accuracy
By counting unique UMIs rather than total reads, UMIs enable more accurate estimation of the true number of input molecules, which is especially important for low-input or highly amplified libraries.
Reducing amplification bias
PCR preferentially amplifies some fragments over others. UMIs help correct for this bias by distinguishing biological molecules from amplification artifacts.
Enhancing variant detection accuracy
In applications such as rare variant or somatic mutation detection, UMIs make it possible to build consensus sequences and distinguish true mutations from PCR or sequencing errors.
Where are UMIs usually located?
UMIs are located next to the index sequence. In this case, if the customer wants to read the UMI sequence, they usually need to run flow cell-based sequencing with a customized configuration. If the customer does not need to read the UMI sequence, standard sequencing can be performed. If the customer wants to read the UMI sequence and requires lane sequencing, please consult APM.
UMIs at the beginning of reads. In this case, the UMI sequence can be read as part of the insert sequence. Please note that for this type of UMI, we do not provide UMI demultiplexing.
Pooling
- What is the requirement of the index numbers/library numbers per lane?
- A: We highly recommend each lane contains above 5 indices on Illumina platform (requirement for both NovaSeq 6000 and NovaSeq X plus).
If the index number is less than 5 on one lane, there is an increased risk of color unbalanced, which may cause unable to demultiplex. Please inform customer of the risk that we are unable to guarantee the demultiplex efficiency. We suggest customers allocate libraries into different lanes and do partial lane sequencing instead of lane sequencing.
- Note: We don’t give suggestions for indices selection, the customer needs to pick indices on their own or refer to the below materials from Illumina. For larger pools, it is recommended to maintain base and color balance for all pooled indexes. Based on the recommended pooling strategies in Illumina Index Adapters Pooling Guide, no more than 50% G base in any index position, and at least 30% C or T in any index position within the pool should be sufficient.
Background information:
When sequencing on a NovaSeq X/X Plus, combine index sequences so that signal is present in both channels for every cycle whenever possible. It is acceptable to have signal only in the green channel from the T or C bases if needed. Illumina recommends avoiding index combinations which only have signal in the blue channel from A or A+G in any given cycle. When sequencing on a two-channel system, either of the first two cycles of the Index Read must start with at least one base other than G. If an Index Read starts with two G bases, signal intensity is not generated and this can cause issues with sequencing this read.
Blue channel—A or C
Green channel—C or T
- Can we pool libraries according to the molarity concentration and volume specified by the customer?
- A: We pool libraries according to sequencing molarity and data amount each library requires. We are unable to pool libraries according to the molarity concentration and volume specified by the customer, we suggest clients pool the libraries by themselves if required.
Sequencing
- Can customer change sequence configuration settings?
- A: NovaSeq6000 and NovaSeq X plus platform can change the sequencing configuration based on flowcell sequencing only. Please note the custom configuration in your quotation and give notice to project manager.
For NovaSeq X Plus PE150, all cycles no more than 338 cycles.
For NovaSeq6000 PE50, all cycles no more than 138 cycles (V1.5). MGI DNBSEQ T7 is unable to change configuration.
By the way, the number of cycles analyzed in Read1 and Read2 is one cycle less than the value entered. For example, to perform a pair-end 150-cycle run (2 X 150bp run), we enter the value of 151 cycles for Read1 and Read2 on the sequence instrument.
- Note: We don't guarantee the normal data output if the customer changes the configuration settings on read length.
If the library prep kit is TruSeq kit, what is the sequence requirement?
- A: If the library is prepared using TruSeq library prep kit or the adapter is compatible with TruSeq adapter sequence, we are unable to guarantee data output. For example, TruSeq Stranded mRNA library.
- Can library with dual index (i5 6bp i7 6bp) / (i5 8bp i7 8bp) or single index (i5 0bp i7 6bp) / (i5 0bp i7 8bp) be sequenced on NovaSeq6000 or NovaSeq X Plus under default configuration?
- A: Yes. When read1 and read2 are 151bp, library with dual index 6+6/8+8 or single index 0+6/0+8 can be sequenced under default configuration. For single index library, i7 index is compulsory. We are unable to guarantee the TAT of single index library sequence on partial lane.
Index shorter than 6bp is unable to do demultiplex.
- How to sequence library with PE adapter (no index)?
- A: Premade library with PE adapter must do lane sequencing. We will provide the un-demultiplex data to customer due to the PE adapter library doesn’t
have index.
Premade library with PE adapter can be sequenced on NovaSeq6000 and NovaSeq X Plus platforms.
Do we have corresponding strategies for sequencing required SE100, PE100, SE75?
- A: We can use standard PE150 configuration to sequence first, then trim the data to the final read length that customer required. Please charge the trim fee according to the price list.
Data Output
- How does Novogene guarantee the data output? A: (1) Lane sequencing:
If all the libraries on the same lane pass library QC, we can guarantee the total data output of a lane, we don’t guarantee the data output for each library. If one of the libraries on the lane fails library QC, we can’t guarantee any data output.
If doesn’t follow the PhiX suggestion of Novogene, we can’t guarantee any data output.
PML sequencing on Novaseq X plus 10B guarantees a data output of 375Gb per lane or 3000Gb per flowcell, subject to the following conditions:
Base-balanced library, with each lane having ≥5 indexes, and all library QC in the PML graded as pass.
The theoretical data output of >375Gb/3000Gb includes index, PhiX data, demultiplexed data, and data that cannot be multiplexed. PML sequencing on Novaseq X plus 25B guarantees a data output of 1Tb per lane or 8Tb per FC, subject to the following conditions:
Base-balanced library, with each lane having ≥5 indexes, and all library QC in the PML graded as pass.
The theoretical data output of >1Tb/8Tb includes index, PhiX data, demultiplexed data, and data that cannot be multiplexed.
(2) Partial lane sequencing:
If the library passes the library QC, we can guarantee the data output. Otherwise, the data output is unable to be guaranteed.
- What is the minimum data requirement? Do we guarantee the sub-library data output in pooled library?
- A: Each library must sequence at least 1Gb (NovaSeq6000 PE150/NovaSeq X Plus PE150) or 1M reads (NovaSeq6000 500cycles/SE50).
For the customer’s pooled library and passed QC, we only guarantee total data output for the pooled library, we don’t promise the data output for each
single sub-library.
- How can we offer BCL file?
- A: If customer needs BCL file, customer needs to order lane or flowcell sequencing.
- What is the relationship between M reads and Gb data for NovaSeq platform? A: Gb data = M pair reads*read length/1000
Read length: PE150= 300 (2*150); PE250=500 (2*250); PE50=100 (2*50); SE50=50
For example: How much Gb data is for 200M pair reads on PE150? A: 200*(2*150)/1000=60 Gb
Does Novogene NovaSeq X Plus use on-board Dragon software?
- A: We currently have no plan to use the Dragon software. And we won’t use Dragon ARO to do the data compression, due to:
Analysis and sequencing cannot be performed at the same time, and the analysis needs to be completed within 6.5 hours, otherwise it will be terminated.
If re-analysis is involved, it is necessary to restart from BCL, and the data must be saved on the NovaSeq X Plus platform.
Special Library Types
What kind of library can be sequenced on MGI DNBSEQ-T7 PE150 platform (Novogene China lab)? A: General Guidelines
The default configuration uses a dual 10 bp index, but we can accept Illumina libraries with dual 8 bp or dual 6 bp indexes.
We do not accept libraries with customized primers.
The data amount for a single library in a single lane should not exceed 200 Gb.
We only accept linear libraries due to circular libraries are prone to hydrolysis, if the customer insists on sending circular libraries, please consult APM.
For lane sequencing of base-unbalanced libraries on the MGI DNBSEQ-T7 platform, PhiX is generally not added; therefore, data output cannot be guaranteed. However, mixing in a proportion of base-balanced libraries can help counterbalance the base composition and improve overall sequencing performance and yield.
We highly recommend each lane contains above 5 indices on MGI DNBSEQ T7 platform.
For Illumina adapter libraries,
We accept Illumina libraries with NEB, TruSeq, or Nextera adapters. We cannot accept small RNA libraries, Riboseq libraries or exosome libraries.
We do not guarantee turnaround time (TAT) for single-index libraries and recommend lane sequencing for these libraries.
In addition to the libraries listed in the table below, other types of single-cell libraries and other unbalanced libraries will need to be evaluated on a case-by-case basis.
Library Type
PMP
Guaranteed Output
TAT
PML
Guaranteed Output
TAT
Notes
WGS
√
-
Meta
√
-
WES
√
-
mRNA (including strand-specific),
Prokaryotic Transcriptome, LncRNA, circRNA
√
-
Hi-C
√
Data volume over 100G will be split across lanes
10x Single-Cell Transcriptome
√
×
√
×
Please consult APM for lane sequencing.
10x VDJ
√
×
√
×
√
Please consult APM for lane sequencing.
Whole Genome Bisulfite Sequencing (WGBS)
√
×
√
×
√
-
Enzymatic Methylation Sequencing (EM-seq)
√
×
-
Reduced Representation Bisulfite Sequencing (RRBS)
√
×
Yield at ~60%
ChIP-seq
√
×
√
×
√
-
For MGI adapter libraries,
We accept both single and dual-index libraries, but different circulation kits are required. (The CSS system has already launched options for the relevant library types. Please note that whether the customer selects MGI single-end or paired-end libraries will be directly pushed to production, so it is critical to select the correct option. If you find that the customer has filled in the information incorrectly, please inform the PC team to synchronize with production and avoid a lack of data output.)
We only accept lane sequencing for MGI libraries, please contact APM if the customer intends to do partial lane sequencing, currently, only the Guangzhou lab can accept PMP sequencing for libraries with MGI adapters, and separate evaluation is required.
3）Libraries other than Fresh Frozen Stereo-seq and C4 libraries will need to be evaluated on a case-by-case basis.
Library Type
PMP
Guaranteed Output
TAT
PML
Guaranteed Output
TAT
Notes
Linear Library with MGI Kit
×
√
×
√
Must be circularized at Novogene
What kits are we using for MGI DNBSEQ-T7 PE150 sequencing?
- A: Circularization kit: MGIEasy App library circularization kit (940000915-00) + MGIEasy universal library conversion kit(App-A), NO: 1000004155 Sequencing primer kit: High throughout pair-end sequencing primer kit (App-D), NO: 1000028550
- What is the sequencing orientation of MGI DNBSEA-T7 PE150?
- A: (1) Read 1 sequencing; MDA reaction; (2) Read 2 sequencing; (3) i5 index and i7 index sequencing
- How to sequence Stereo-seq Transcriptomics library, and what is the data output?
- A: Fresh Frozen Stereo-seq (except V1.3) Transcriptomics library must sequence on MGI DNBSEQ T7 PE100 with read1 50bp and read2 100bp configuration. But due to read1 has 15bp dark reactions, the real data of Stereo-seq Transcriptomics library read1 will be 35bp.
We recommend 1 billion reads per sample, around 135Gb data/sample (1 billion reads * (100+35)/1000). Suggest to pool 3 samples on one PE100 flowcell. The estimate data output is 4000M.
FFPE Stereo-seq transcriptomics and Fresh Frozen Stereo-seq V1.3 libraries require the use of a PE75 sequencing strategy, and flow cell sequencing is required. The estimate data output is Stereo-seq fresh frozen: 4000M, Stereo-seq FFPE: 5000M, reagents need to be procured based on the specific project’s PO. Please notify us one month in advance before sending samples.
For single-cell libraries from 10x Genomics, which sequence platform and configuration should customer choose?
- A: We use Cell Ranger to do the demultiplex. Each sample index is a mix of 4 different sequences to balance across all 4 nucleotides. If multiple samples are pooled in a sequence lane, the sample index name (i.e. Single Index Plate_ Set_well ID) is needed in the sample sheet used for generating FASTQs with Cell Ranger. Samples utilizing the same sample index should not be pooled together or run on the same flow cell lane, as this would not enable correct sample demultiplexing.
We are unable to promise the Q30 of single cell libraries sequenced on default sequence configuration. For example, single cell 3’ gene expression
library requires 28+10+10+91, but sequenced on partial lane of PE150 (151+10+10+151), the Q30 will be low due to the reads will contain poly A. The Q30 will improve after data trimming.
- Note: The following images are for displaying the library structure only. The data we deliver is complete PE150/PE50 sequencing data. Data trimming requires an additional fee, please refer to the price list.
Chromium Single Cell 3ʹ Gene Expression Dual Index Library (NovaSeq PE150: 28+10+10+91, strongly recommend 50,000 or 100,000 reads pairs per cell, minimum 20,000 reads pairs per cell)
Chromium Next GEM Single Cell Multiome ATAC + Gene Expression (will have two libraries for the same sample: ATAC library and 3’ gene
expression library)
Chromium Single Cell Multiome ATAC Library (NovaSeq PE50 flowcell seq: 50+8+24+50), 8bp Spacer + 16bp 10x barcode=24bp The protocol suggests adding 1% PhiX for the Chromium Single Cell Multiome ATAC Library for NovaSeq PE50 flowcell sequencing.
Chromium Single Cell Multiome Gene Expression Library (NovaSeq PE150: 28+10+10+91)
- Note: For both the 10x Multiome ATAC and 10x sc-ATAC library types, we recommend PE50 FC sequencing. However, if a customer requests lane sequencing, we now also offer lane sequencing for these library types. Please note that currently, lane sequencing for these library types is only available on the NovaSeq X Plus platform on 25B, and can only be performed at the Tianjin lab. (This is not a technical limitation, but because only one sequencer
at our facility has been configured for FC with the setup of 151+10(i7) +24(i5) +151.) We recommend adding PhiX at a ratio of 10%. Please note that it is not recommended to pool 10x ATAC and 10x 3' libraries on the same lane, as the difference in library sizes may lead to uneven data output.
Chromium Single Cell ATAC Library (NovaSeq PE50 flowcell seq: 50+8+16+50), 16bp 10x barcode
Visium HD Spatial Gene Expression Library (We suggest doing PE150 partial lane seq: 43+10+10+50) on NovaSeq 6000 or NovaSeq X Plus, please check with APM for availability of lane sequencing.
Turnaround Time
- How long is the TAT for single index premade library?
- A: Pooling single-indexed and dual-indexed libraries is not recommended and supported by Illumina, so we highly recommend customers use dual indexes instead during their library preparation. We can’t guarantee the TAT for single index premade library, single indexed libraries will have a delayed pooling TAT of at least a month.
Turnaround Time of premade library sequencing. A:
Product No.
Product Name
Sample/ Lane No.-min
Sample/ Lane No.-max
TAT(working days)
RSS001103
Pre-made libraries partial lane sequencing (NovaSeq X Plus PE150)
1
30
20
RSS001103
Pre-made libraries partial lane sequencing (NovaSeq X Plus PE150)
31
50
25
RSS001103
Pre-made libraries partial lane sequencing (NovaSeq X Plus PE150)
51
100
30
RSS001103
Pre-made libraries partial lane sequencing (NovaSeq X Plus PE150)
101
∞
40
RSSQ00703
Pre-made libraries lane sequencing (NovaSeq PE250)
1
10
13
RSSQ00703
Pre-made libraries lane sequencing (NovaSeq PE250)
11
30
17
RSSQ00703
Pre-made libraries lane sequencing (NovaSeq PE250)
31
∞
30
RSSQ00803
Pre-made libraries lane sequencing (NovaSeq SE50)
1
10
13
RSSQ00803
Pre-made libraries lane sequencing (NovaSeqSE50)
11
30
17
RSSQ00803
Pre-made libraries lane sequencing (NovaSeq SE50)
31
∞
30
RSSQ00903
Pre-made libraries lane sequencing (NovaSeqPE50)
1
10
13
RSSQ00903
Pre-made libraries lane sequencing (NovaSeqPE50)
11
30
17
RSSQ00903
Pre-made libraries lane sequencing (NovaSeqPE50)
31
∞
30
RSSQ01203
Pre-made libraries lane sequencing (NovaSeq X Plus PE150)
1
10
13
RSSQ01203
Pre-made libraries lane sequencing (NovaSeq X Plus PE150)
11
30
17
RSSQ01203
Pre-made libraries lane sequencing (NovaSeq X Plus PE150)
31
∞
30
RSSQ01503
Pre-made Libraries Lane Sequencing (NovaSeq X Plus 25B PE150)
1
30
20
RSSQ01503
Pre-made Libraries Lane Sequencing (NovaSeq X Plus 25B PE150)
31
50
25
RSSQ01503
Pre-made Libraries Lane Sequencing (NovaSeq X Plus 25B PE150)
51
100
30
RSSQ01903
Pre-made libraries lane sequencing (T7 PE150)
1
30
20
RSSQ01903
Pre-made libraries lane sequencing (T7 PE150)
31
50
25
RSSQ01903
Pre-made libraries lane sequencing (T7 PE150)
51
100
30
RSSQ02903
Pre-made Libraries Lane Sequencing (T7 PE100)
1
20
15
RSSQ02903
Pre-made Libraries Lane Sequencing (T7 PE100)
21
40
20
RSSQ02903
Pre-made Libraries Lane Sequencing (T7 PE100)
41
∞
40
- Note: For Pre-made libraries lane sequencing (T7 PE75), please use the same product number as Pre-made libraries lane sequencing (T7 PE100).
Library Size
Sequencing strategy
Library size (insert + adaptors (120bp) +/- 50 bp for optimal results *
SE 50/PE 50
<700bp
PE 150
300-700bp (Tianjin Lab and Beijing Lab);
>300bp (Singapore and Japan lab)
500 cycles
>370bp
- Note: * Does not apply to small RNA library.
If the library size is not within the standard range of the sequencing strategy, the library will not pass our library QC, and we cannot guarantee the data output and quality.
Applications
Sequencing Strategy (NovaSeq)
Application
PE150 (NovaSeq X Plus 10B/25B)
WGS, WES, PAWGS, mRNA-seq, LncRNA, WGBS, ChIP-seq/RIP-seq,
Metagenomics, Metatranscriptome, 10x single cell RNA seq
500 cycles (NovaSeq6000 SP)
Amplicon, PCR product (~450bp)
SE50 (NovaSeq6000 SP)
Small RNA, ChIP-seq/RIP-seq (optional), Ribo seq
PE50 (NovaSeq6000 SP)
10x ATAC seq
Other strategies
Please evaluate based on library type and structure
PhiX Suggestion
We only add PhiX when doing lane/flowcell sequencing. We are unable to add PhiX when doing partial lane sequencing.
When pooling multiple types of premade libraries on one lane, please use the highest PhiX ratio among the multiple library types.
Library Base Balance
Library Type
X Plus-10B PhiX
X Plus-25B PhiX
Base unbalanced library
Premade-10X Whole Genome Library
10%
5%
Premade-10X 3 prime Single Cell Transcriptome Library
5%
1%
Premade-10X 5 prime Single Cell Transcriptome Library
5%
1%
Premade-10X VDJ Library
10%
5%
Premade-ATAC-Seq Library
20%
Premade-Methylation Library
15%
5%
Premade-PCR Product Library
40%
Premade-Small RNA Library
10%
5%
Premade-Single Cell RNA Library - NOT 10X
20%
Premade-RAD Library/GBS Library
20%
Premade-NanoString DSP Library
≥25%
20%
Premade-Amplicon Metagenomic Library
≥30%
Premade-Others (with fixed bases)
20%
Premade-10X ATAC Library
20%
Premade-10X ATAC (Multiome) Library
20%
Premade-10X Visium Library
10%
Premade-10X 5 prime Feature Barcode Library
5%
1%
Premade-10X 3 prime Feature Barcode Library
5%
1%
Premade-10X Single Cell Gene Expression Flex Library
20%
Premade-Nascent RNA-aimed Library
20%
Premade-BD Single-Cell Multiplexing (SMK)/Sample Tag Library
20%
Premade-BD AbSeq Library
20%
Premade-BD Whole Transcriptome Analysis (WTA) Library
20%
Premade-Parse Evercode Whole Transcriptome (WT) Library
20%
Premade-Parse Evercode BCR Library
20%
Premade-Parse Evercode TCR Library
20%
Premade-SeekOne Single-Cell Library
20%
Premade-MobiCube Single-Cell Library
5%
Premade-PCR Product/CRISPR Library
35%
Premade-CUT&RUN/CUT&Tag Library
20%
Base balanced library
Premade-ChIP-seq
0%
Premade-Hi-C Library
0%
Premade-Shotgun Metagenomic Library
0%
Premade-WES Library
0%
Premade-WGS Library (Human)
0%
Premade-Others (without fixed bases)
0%
Premade-WGS Library (Animal or Plant)
0%
Premade-WGS Library (Microbe)
0%
Premade-Eukaryotic RNA-seq Library
0%
Premade-Truseq Stranded mRNA/Total RNA Library
0%
Premade-Human Target Region Library
0%
Premade-PCR-free WGS Library (Animal or Plant)
0%
Premade-PCR-free WGS Library (Human)
0%
Premade-PCR-free WGS Library (Microbe)
0%
Premade-RIP-seq or CLIP-seq Library
0%
Premade-LncRNA Library
0%
Adapter Information
Adaptor must match with Illumina;
Index must be forward orientation;
Library structure:
Library Kit
Adapter
Library sequence
Multiplexing adapter
（NEB）
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGAGATCTACACTCTTTCCCTACACGACGCTCTTCCGATCTXXXXXXXXXXXXXX AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC（index）ATCTCGTATGCCGTCTTCTGCTTG-P7'
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTCTAGATGTGAGAAAGGGATGTGCTGCGAGAAGGCTAGAXXXXXXXXXXXXXX TCTAGCCTTCTCGTGTGCAGACTTGAGGTCAGTG（index）TAGAGCATACGGCAGAAGACGAAC-P7
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAGAT（index）GTGACTGGAGTTCAGACGTGTGCTCTTCCGATCTXXXXXXXXXXXXXX AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGTAGATCTCGGTGGTCGCCGTATCATT-P5'
Nextera Index –
Kit adapter
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGAGATCTACAC[i5]TCGTCGGCAGCGTCAGATGTGTATAAGAGACAGXXXXXXXXXXXXXXXX CTGTCTCTTATACACATCTCCGAGCCCACGAGAC[i7]ATCTCGTATGCCGTCTTCTGCTTG-P7'
primer
（Illumina）
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTCTAGATGTG[i5]AGCAGCCGTCGCAGTCTACACATATTCTCTGTCXXXXXXXXXXXXXXX GACAGAGAATATGTGTAGAGGCTCGGGTGCTCTG[i7]TAGAGCATACGGCAGAAGACGAAC-P7
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAGAT[i7]GTCTCGTGGGCTCGGAGATGTGTATAAGAGACAGXXXXXXXXXXXXXXX CTGTCTCTTATACACATCTGACGCTGCCGACGA[i5]GTGTAGATCTCGGTGGTCGCCGTATCATT
PE adapter primer (without index)
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGAGATCTACACTCTTTCCCTACACGACGCTCTTCCGATCTXXXXXXXXXXX AGATCGGAAGAGCGGTTCAGCAGGAATGCCGAGACCGATCTCGTATGCCGTCTTCTGCTTG-P7’
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTCTAGATGTGAGAAAGGGATGTGCTGCGAGAAGGCTAGAXXXXXXXXXXX TCTAGCCTTCTCGCCAAGTCGTCCTTACGGCTCTGGCTAGAGCATACGGCAGAAGACGAAC-P7
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAGATCGGTCTCGGCATTCCTGCTGAACCGCTCTTCCGATCTXXXXXXXXXXX AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGTAGATCTCGGTGGTCGCCGTATCATT-P5'
TruSeq DNA HT/TruSeq Stranded RNA HT
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGAGATCTACAC[i5]ACACTCTTTCCCTACACGACGCTCTTCCGATCTXXXXXXXXXXX GATCGGAAGAGCACACGTCTGAACTCCAGTCAC[i7]ATCTCGTATGCCGTCTTCTGCTTG-P7’
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTCTAGATGTG[i5]TGTGAGAAAGGGATGTGCTGCGAGAAGGCTAGAXXXXXXXXXXX CTAGCCTTCTCGTGTGCAGACTTGAGGTCAGTG[i7]TAGAGCATACGGCAGAAGACGAAC-P7
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAGAT[i7]GTGACTGGAGTTCAGACGTGTGCTCTTCCGATCXXXXXXXXXXX AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT[i5]GTGTAGATCTCGGTGGTCGCCGTATCATT-P5'
TruSeq (Single index)
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGAGATCTACACTCTTTCCCTACACGACGCTCTTCCGATCTXXXXXXXXX GATCGGAAGAGCACACGTCTGAACTCCAGTCAC（index）ATCTCGTATGCCGTCTTCTGCTTG-P7 ’
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTCTAGATGTGAGAAAGGGATGTGCTGCGAGAAGGCTAGAXXXXXXXXX CTAGCCTTCTCGTGTGCAGACTTGAGGTCAGTG（index）TAGAGCATACGGCAGAAGACGAAC-P7
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAGAT(index)GTGACTGGAGTTCAGACGTGTGCTCTTCCGATCXXXXXXXXX AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGTAGATCTCGGTGGTCGCCGTATCATT-P5'
TruSeq Small RNA Sample Prep Kits
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGAGATCTACACGTTCAGAGTTCTACAGTCCGAXXXXXXXXXXXXXX TGGAATTCTCGGGTGCCAAGGAACTCCAGTCAC（index）ATCTCGTATGCCGTCTTCTGCTTG-P7'
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTCTAGATGTGCAAGTCTCAAGATGTCAGGCTXXXXXXXXXXXXX ACCTTAAGAGCCCACGGTTCCTTGAGGTCAGTG(index)TAGAGCATACGGCAGAAGACGAAC-P7
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAGAT(index)GTGACTGGAGTTCCTTGGCACCCGAGAATTCCAXXXXXXXXXXXXX TCGGACTGTAGAACTCTGAACGTGTAGATCTCGGTGGTCGCCGTATCATT-P5'
P5→P7'
（5'-3'）
P5-AATGATACGGCGACCACCGACAGGTTCAGAGTTCTACAGTCCGACGATCXXXXXXXXXXXXTCGTATGCCGTCTTCTGCTTG-P7'
Oligonucleotide
sequences for the v1 and v1.5
P5'→P7
（3'-5'）
P5'-TTACTATGCCGCTGGTGGCTGTCCAAGTCTCAAGATGTCAGGCTGCTAGXXXXXXXXXXXXAGCATACGGCAGAAGACGAAC-P7
Small RNA Kits
P7→P5’
（5'-3'）
P7-CAAGCAGAAGACGGCATACGAXXXXXXXXXXXXGATCGTCGGACTGTAGAACTCTGAACCTGTCGGTGGTCGCCGTATCATT-P5'
- Note:
Underline part is the P5/P7 adapter oligo.
Blue part is the Read1 sequence primer.
Green part is the Read 2 sequence primer.
Every kit has three rows:
P5→P7', base sequence is 5’-3', this is the real sequence orientation;
P5'→P7, base sequence is 3’-5', complementary pairing with the first row;
The second row is the reverse complement sequence of the third row.
Index Orientation
Index sequences are used for demultiplexing. Index 1 (i7 index) is required, and index 2 (i5 index) is optional.
The correct orientation of the indexes that should be filled in your Sample Information Form（SIF）is P5 to P7, 5’ to 3’, as the red arrows show in the
picture above.
For i7 index, please refer to "i7 bases for sample sheet" in your library preparation guide. For i5 index, please select "i5 Bases for Sample Sheet NovaSeq 6000 with v1.0/v1.5 reagent kits”. (the i5 bases should be consistent with Hiseq2000/2500)
We use Illumina V1.5 reagents for sequencing (workflow B/reverse complement) but our demultiplexing software requires the index sequence in V1.0 orientation (workflow A/forward).
The reading and demultiplex direction of NovaSeq X Plus is the same as that of NovaSeq6000.
If premade library adapter is compatible with Illumina: Dual index library please fill in i7 index + i5 index;
Single index library with i7 index + P5 common sequence, please fill in i7 index + TCTTTCCC; Single index library with i7 index + P5 random sequence, please fill in i7 index;
Library without index (PE adapter), library must compatible totally with PE adapter.
(If primer in P5 adapter has TCTTTCCC, it means P5 common sequence; if not, it means P5 random sequence.
Customized Sequencing Primer Requirements
If sequence primer is from customer:
For customized read1&read2 primer (either or both) - NovaSeq6000 and NovaSeq X Plus must do flowcell seq.
Sequence
Platform
Sequencing Primer
Concentration
Volume
Note
NovaSeq X Plus PE150 (10B)*
Read 1 primer
100 μmol/L
≥50ul/flowcell
FC sequencing
Index primer
≥50ul/flowcell
FC sequencing
Read 2 primer
≥50ul/flowcell
FC sequencing
NovaSeq6000 SP 500 cycles
Read 1 primer
100 μmol/L
≥30ul/flowcell
FC sequencing
Index primer
≥50ul/flowcell
FC sequencing
Read 2 primer
≥30ul/flowcell
FC sequencing
NovaSeq6000 SP PE50
Read 1 primer
100 μmol/L
≥30ul/flowcell
FC sequencing
Index primer
≥50ul/flowcell
FC sequencing
Read 2 primer
≥30ul/flowcell
FC sequencing
NovaSeq6000 SP SE50
Read 1 primer
100 μmol/L
≥30ul/flowcell
FC sequencing
Index primer
≥50ul/flowcell
FC sequencing
- Note:
*For Novaseq X Plus custom sequencing primer libraries:
If the custom primers do not have overlap with Illumina's primer sequences, we can add the custom primers directly to the original primers.
If the custom primers have overlap with Illumina's primer sequences, we need to replace the original primers, the additional primer balancing reagents and charge are needed. There is no stock in lab now, please give advance notice to APM and project manager.
We don’t promise data output with custom primers.
Illumina item No.: 20100055-NovaSeq X Series Custom-Primer Buffer
Turnaround time of kit purchasing: now over one month (please contact APM for details)
Novogene Product Manual
mRNA Sequencing
AMEA 2024.08
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclose to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
Novogene Product Manual – mRNA Sequencing
Revision Number
2024 V1.0
Issue Date
Aug 2024
Prepared by
Tianran Shi
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Pg 5 – Add RNA extraction sample requirement of Plant and Bacteria Pg 6 – mRNA seq sample requirement update
Pg 10 – Add oncogene analysis to Quantification Medical analysis contents Pg 11 – FFPE TruSeq RNA-seq uses Medical RNA analysis pipeline
Pg 14 – FAQ 7 RNA library prep and analysis of Virus sample
Pg 17 – FAQ 13 RNA Denovo analysis applies to eukaryotic species only
Pg 18 – FAQ 10 Comparisons of Quantification and Standard analysis package Pg 20 – FAQ 18 Functions of NovoMagic platform
Pg 23 – FAQ 3 Differences between meta-transcriptome and Dual RNA seq Pg 24-26 – Add “Dual RNA seq” product
Tianran Shi
June 2023
2023 V2.0
Pg 12 - FAQ 1 Add FFPE TruSeq library type Pg 19 - FAQ 15 Add PDX analysis pipeline
Pg 22 – Update the RIN value sample requirement of metatranscripome Pg 23 - Update analysis contents of metatranscripome
Tianran Shi
Aug 2023
2023 V3.0
Pg 5-6 – Update the sample requirement of RNA extraction
Pg 7 – Add the sample requirement of Globin Clear and Globin Zero
Tianran Shi
Nov 2023
2024 V1.0
Delete UMI mRNA/sRNA Sequencing product, this service is discontinued
Pg 22 – Add FAQ 19 about project data retention time in NovoMagic Pg 24 – add “soil” RNA extraction sample requirement
Pg 29 – Delete FAQ3 - the price for dual RNA seq Pg 33 – update TPM analysis price and results
Tianran Shi
Aug 2024
Contents
mRNA Sequencing6
RNA Extraction (SG Outsource)6
## Sample Requirements7
Sequencing Strategy and Turnaround Time8
Analysis Contents9
Eukaryotic transcriptome quantification analysis9
Eukaryotic transcriptome standard analysis10
Eukaryotic transcriptome de novo standard analysis12
Prokaryotic transcriptome standard analysis13
## FAQ14
Meta-transcriptome Sequencing24
RNA Extraction (SG Outsource)24
## Sample Requirements25
Sequencing Strategy and Turnaround Time25
Analysis Contents25
## FAQ26
Dual RNA sequencing28
## Sample Requirements28
Sequencing Strategy and Turnaround Time28
Analysis Contents29
## FAQ29
Appendix 1 Special Requirement Evaluation Form for CAP lab31
Appendix 2 Price of Customized /After-sale Analysis32
mRNA Sequencing
Messenger RNA (mRNA) is the RNA that carries information from DNA to the ribosome, the sites of protein synthesis (translation) in the cell. The coding sequence of the mRNA determines the amino acid sequence in the protein that is produced. The eukaryotic mRNA sequencing aims at the mRNA (protein-coding RNA) of all kinds of eukaryotes, short as mRNA-Seq.
The prokaryotes are mostly single-celled organisms and lack membrane-bound nuclei and other organelles, which means the processes of transcription, translation, and mRNA degradation can all occur simultaneously. Prokaryotic transcription often covers more than one gene and produces polycistronic mRNAs that specify more than one protein, which is a main difference compared with eukaryotic transcripts. Prokaryotic RNA sequencing reveals the presence and quantity of RNA at a given moment, by analyzing the changing cellular transcriptome.
RNA Extraction (SG Outsource)
Sample types
Recommend Input
Transportation
Human Blood
Blood must be collected in PAXgene Tubes following supplier’s guidelines. Store in -80°C freezer
Follow tube specification, evaluate case by case
Tissue sample (Human or Animal)
Tissue must be wash with 1XPBS to remove all traces of blood Weight: 30mg
Preferably stored in RNAlater. Snap Frozen in liquid nitrogen after 1XPBS wash and weighting
Store in -80°C freezer
3 replicates per sample to be sent
Dry Ice
Plant
Young leaves/needles preferred Weight: 100mg-200mg wet weight
Fresh plants samples: snap frozen in liquid nitrogen. If liquid nitrogen is not available, store freshly in freshly made 80% v/v ethanol
Store in -80°C freezer
3 replicates per sample to be sent
Dry Ice
Cultured Cells
Pellet form
Preferably stored in RNA
Dry Ice
1 x 107
Storage in -80°C freezer
3 replicates per sample to be sent
Bacteria
50-100mg
Storage in -80°C freezer
3 replicates per sample to be sent
Dry Ice
Fungi
Filamentous Fungi material Weight: 100mg
Snap frozen in liquid nitrogen Store in -80°C freezer
3 replicates per sample to be sent
Dry Ice
- Note: Please provide more information for evaluation: sample amount, sample pictures, sample preservation solution and so on.
## Sample Requirements
Library Type
Sample Type
Remarks
Amount
RIN
Volume
Concentra tion
Purity (NanoDropTM/ Agarose gel)
Eukaryotic mRNA library (poly A enrichment)
Total RNA (Eukaryotic)
Strongly Recommended
≥ 400 ng
≥ 4.0 (animals/ plants & fungi)
≥ 20 μL
≥ 10 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 200 ng
Total RNA (Blood)
Required
≥ 400 ng
≥ 5.0
≥ 20 μL
≥ 20 ng/μL
Double strand cDNA
Required
≥ 100 ng
-
≥ 20 μL
≥ 5 ng/μL
Fragments distributing between 400-5000bp, with the main peak at
~2000bp
Eukaryotic directional mRNA library (poly A
enrichment)
Total RNA (Eukaryotic)
Strongly Recommended
≥ 800 ng
≥ 5.8 (animals/ plants & fungi/blood)
≥ 20 μL
≥ 20 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 400 ng
Prokaryotic directional RNA library (rRNA
removal)
Total RNA (Prokaryotic)
Strongly Recommended
≥ 1 μg
≥ 6.0
≥ 20 μL
≥ 25 ng/μL
OD260/280 > 2.0
No degradation, no contamination,
no high content of 5S
Required
≥ 500 ng
Eukaryotic mRNA non-directional library (poly A enrichment;
SMARTer kit)
Low Input total RNA (Eukaryotic)
-
1 ng~10 ng
-
OD260/280 > 2.0
No degradation, no contamination
FFPE RNA library
(TruSeq RNA Exome Panel)
FFPE RNA
Human Only
≥ 200 ng
-
≥ 15 μL
≥ 10 ng/μL
DV200>50
Globin Clear non-directional library
Human blood total RNA
Strongly
Recommended
≥ 800 ng
≥ 5.0
≥ 20 μL
≥ 20 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 400 ng
Globin Clear directional library
Human blood total RNA
Strongly
Recommended
≥ 800 ng
≥ 5.0
≥ 20 μL
≥ 20 ng/μL
Required
≥ 400 ng
Globin Zero directional library
Human/Mous e/Rat blood
total RNA
Strongly Recommended
≥ 1 μg
≥ 5.5
≥ 20 μL
≥ 25 ng/μL
Required
≥ 500 ng
Sequencing Strategy and Turnaround Time
Sample Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
Eukaryotic RNA
NovaSeq PE150
30M-50M reads/sample
9-15 Gb/sample
WOBI
WBI
15-18 working days
20 working days (quantification)
25 working days (standard analysis with reference)
42 working days (de novo)
Prokaryotic RNA
NovaSeq PE150
10M reads/sample 3 Gb/sample
15-18 working days
30 working days
Analysis Contents
Eukaryotic transcriptome quantification analysis
Quantification Analysis (Eukaryotic, Agricultural-with reference)
Software
Data Quality Control: filtering reads containing adapter or with low quality
Fastp
Statistics Analysis of Data Production and Quality
-
Mapping Reads to Reference Genome
HISAT2
Gene Expression Quantification
FeatureCounts
Correlation analysis (For biological replicates only)
-
Differential Expression Analysis (two or more groups of samples)
DESeq2(with biological replicates)
/EdgeR(without biological replicates)
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
GSEA Enrichment Analysis of Expressed Genes (two or more groups of samples)
GSEA
Protein Protein Interaction Analysis
BLAST
Quantification Analysis (Eukaryotic, Medical-human, mouse only)
Software
Data Quality Control: filtering reads containing adapter or with low quality
Fastp
Statistics Analysis of Data Production and Quality
-
Mapping Reads to Reference Genome
HISAT2
Gene Expression Quantification
FeatureCounts
Correlation analysis (For biological replicates only)
-
Differential Expression Analysis (two or more groups of samples)
DESeq2(with biological replicates)
/EdgeR(without biological replicates)
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
Reactome Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
DO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of
samples and only for human samples)
ClusterProfiler
DisGeNET Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples and only for human samples)
ClusterProfiler
GSEA Enrichment Analysis of Expressed Genes (two or more groups of samples)
GSEA
Oncogene Functional Annotation analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
COSMIC
Protein Protein Interaction Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
BLAST
Eukaryotic transcriptome standard analysis
Standard Analysis (Eukaryotic, Agricultural-with reference)
Software
Data Quality Control: filtering reads containing adapter or with low quality
Fastp
Statistics Analysis of Data Production and Quality
-
Mapping Reads to Reference Genome
HISAT2
Novel Gene Prediction
StringTie
Alternative Splicing Analysis
rMATs
SNP/InDel Analysis
GATK,SNPEff
Gene Expression Quantification
FeatureCounts
Correlation analysis (For biological replicates only)
-
Differential Expression Analysis (two or more groups of samples)
DESeq2(with biological replicates)
/EdgeR(without biological replicates)
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
GSEA Enrichment Analysis of Expressed Genes (two or more groups of samples)
GSEA
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
Protein Protein Interaction Analysis
BLAST
Standard Analysis (Eukaryotic, Medical-human, mouse only) Standard Analysis (FFPE TruSeq Exome RNA-seq)
Software
Data Quality Control: filtering reads containing adapter or with low quality
Fastp
Statistics Analysis of Data Production and Quality
-
Mapping Reads to Reference Genome
HISAT2
Gene Expression Quantification
FeatureCounts
Differential Expression Analysis (two or more groups of samples)
DESeq2(with biological replicates)
/EdgeR(without biological replicates)
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more
groups of samples)
ClusterProfiler
Reactome Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
DO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples and only for human samples)
ClusterProfiler
DisGeNET Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples and only for human samples)
ClusterProfiler
GSEA Enrichment Analysis of Expressed Genes (two or more groups of samples)
GSEA
Protein Protein Interaction Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
BLAST
Oncogene Functional Annotation analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
COSMIC
Alternative Splicing (AS) Quantification and Differential Expression Analysis
rMATS
SNP/InDel Analysis
GATK,SNPEff/ANNOVAR
Fusion Gene Analysis (for tumor sample and cancer cell line)
STAR-Fusion
Eukaryotic transcriptome de novo standard analysis
Standard Analysis (Eukaryotic, de novo transcriptome)
Software
Data Quality Control: filtering reads containing adapter or with low quality
Fastp
Statistics Analysis of Data Production and Quality
-
De novo Transcriptome Assembly
Trinity
Gene Functional Annotation Using Seven Databases (NR, NT, KOG, KO, Swiss-Prot, GO and
PFAM)
blast+, Diamond, hmmscan, KAAS,
blast2go
GO, COG, KEGG Classification
-
CDS Prediction
BLAST, ESTScan
SNP/INDELs calling
Samtools
SSR Analysis
MISA, primer3
Gene Expression Analysis
RSEM
Correlation analysis (For biological replicates only)
-
Differential Expression Analysis (two or more groups of samples)
DESeq2(with biological replicates)
/edgeR (without biological replicates)
Enrichment Analysis of differentially expressed coding genes: GO Enrichment
KEGG Pathway Enrichment
GOSeq, topGO, hmmscan KOBAS
Protein Protein Interaction Analysis of differentially expressed coding genes
BLAST
Prokaryotic transcriptome standard analysis
Standard Analysis (Prokaryotic RNA sequencing)
Software
Data Quality Control: filtering reads containing adapter or with low quality
Fastp
Evaluation of Data Quality
-
Mapping Reads to Reference Genome
Bowtie
Gene Expression Analysis
FeatureCounts
Novel Transcript Prediction
Rockhopper
Differential Expression Analysis (two or more groups of samples)
DESeq2(with biological replicates)
/EdgeR (without biological replicates)
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
ClusterProfiler
GSEA Enrichment Analysis of Expressed Genes (DEGs) (two or more groups of samples)
GSEA
Operon, Promoter and TSS/TTS Prediction
Rockhopper
SD Sequence prediction
RBSfinder
Rho-independent Terminator Sequence Prediction
TranstermHP
sRNA Secondary Structure Prediction
RNAfold
sRNA Targeted Gene Prediction
IntaRNA
## FAQ
- What is the library size of RNA libraries (Eukaryotic non-directional mRNA library, Eukaryotic directional mRNA library and Prokaryotic directional library)?
- A: Eukaryotic RNA library—250-300 bp insert non-directional / directional library (polyA capture).
Prokaryotic RNA library—250-300 bp insert directional library with rRNA removal. FFPE TruSeq RNA library—directional library (Exome capture).
- Can SMART-Seq V4 Ultra Low Input RNA kit be used to do the amplification for directional library?
- A: No, SMART-Seq V4 Ultra Low Input RNA kit is for non-directional mRNA library only, not applicable for directional mRNA or lncRNA library. SMART-Seq V4 Ultra Low Input RNA kit product manual: https://www.takarabio.com/a/114896
- Can Novogene add ERCC Spike-in?
- A: Sorry, we can’t offer the ERCC Spike-in service. We are able to accept the RNA sample with ERCC added by customers themselves. The full name of ERCC is External RNA controls consortium. The ERCC RNA Spike-In Control Mixes are pre-formulated sets of 92 polyadenylated transcripts from the ERCC plasmid reference library.
The ERCC RNA Spike-In Mix (Part no 4456740) includes Spike-In Mix 1 alone; it can be used to assess platform dynamic range and lower limit of detection.
The ERCC ExFold RNA Spike-In Mixes (Part no 4456739) include both Spike-In Mix 1 and Spike-In Mix 2. In addition to the performance measurements described above for the ERCC RNA Spike-In Mix, this kit can be used to assess the accuracy of measurements of differential gene expression on your platform.
Do we need to remove the Globin mRNA in human blood sample? What is the difference between Globin clear and Globin zero?
- A: Globin mRNA accounted for more than 76% of the total mRNA. Therefore, if globin mRNA and ribosomal RNA are not completely removed, the analysis of low abundance transcripts will be seriously affected. We suggest customer to remove Globin mRNA for blood mRNA sequencing. Customers can also choose to remove it or not.
Globin clear - GlOBINclearTM Kit (Thermo Fisher, Catalog number: AM1980, 20 preps)
The GlOBINclearTM—Human Kit uses a novel, non-enzymatic technology that rapidly depletes >95% of the alpha and beta globin mRNA
from total RNA preparation derived from whole blood. Novogene only offers human GlOBINclearTM Kit now.
Globin Zero - TruSeq Stranded Total RNA with Ribo-Zero Globin (Illumina, 48 preps or 96 preps) Simultaneous removal of rRNA and globin mRNA while retaining the mRNA and noncoding RNA population.
The goal of this kit is to wash and resuspend magnetic beads, which then bind to removal probes hybridized to rRNA and globin mRNA, producing an RNA sample ready for library prep.
This kit couples the benefits of Ribo-Zero ribosomal RNA reduction chemistry with RNA sequencing (RNA-Seq) technology for whole-transcriptome analysis of human, mouse, or rat samples.
Do we offer BGI DNBSEQ-T7 sequence service for RNA products?
- A: Yes, we offer DNBSEQ-T7 sequence service for eukaryotic mRNA sequencing (Eukaryotic non-directional mRNA library and Eukaryotic directional mRNA library), the sample requirement is same as NovaSeq. TAT is a bit longer than Illumina platform. We will do cyclization to the illumine library using Universal Library Conversion Kit (App-A) Cat. No.: 1000004155.
What kind of library prep kit is recommended for FFPE RNA samples?
- A: TruSeq RNA Exome, previously known as the TruSeq RNA Access Library Prep Kit, which captures the coding transcriptome/ RNA exome. Recommend 12Gb data (standard product). This kit is for human only.
We offer TruSeq RNA Exome library prep for FFPE RNA sample only. Don’t offer the mRNA-seq and lncRNA-seq service for FFPE RNA sample.
The standard analysis pipeline for FFPE TruSeq Exome is same with mRNA(medical) standard analysis pipeline.
- Can we offer other data output rather than 12Gb for FFPE RNA samples with TruSeq RNA Exome kit?
- A: For TruSeq RNA Exome kit, if client requires other data output rather than 12Gb, please fill in ‘Special requirement Evaluation Form for CAP lab’ about the detail information and inquiry from APM. Sample number and submit batches plans are required for lab’s evaluation. Due to it is non-standard product from CAP lab, the price will be higher than standard product with 12Gb data.
Please refer to Appendix 1 form for the detail.
- What is DV200?
- A: The DV200 is the percentage of RNA fragments >200 nucleotides. Although RIN values for these samples lie within a relatively narrow range (2.3-3.2), the size distribution of the RNA varies greatly among the samples.
We use DV200 result for FFPE RNA samples quality control.
Are we able to do RNA library prep and sequence to virus sample?
- A: We don’t have the RNA library prep process for virus. For non-human infected virus, we suggest customer to send double strand cDNA to do library preparation. For human infected virus, we suggest customer to do library preparation by themselves, Novogene can provide sequencing service for premade library. And we don’t have analysis pipeline for virus, we are unable to provide analysis for virus sample.
- How to search reference genome?
- A: (1) NCBI (National Center for Biotechnology Information) https://www.ncbi.nlm.nih.gov
(2) Ensemble database http://asia.ensembl.org/index.html
First, check the assembly level of genome, such as contig level, scaffold level or chromosome level. Generally, the genome assemble to scaffold level or chromosome level is more reliable.
Secondly, we need to find the GFF or GTF annotation file and evaluate the completeness of gene annotation. The annotation file needs to have annotation information of gene, transcript, CDS and exon areas (at least exon or CDS. If there is no exon, a CDS will be regarded as an exon for analysis). If the above information is complete and available, the preliminary evaluation of this reference genome can be used.
- What is the difference of FPKM/RPKM/TPM?
- A: FPKM (Fragments Per Kilobase Million); FPKM is used in dual reads sequencing.
RPKM (Reads Per Kilobase Million); RPKM is used in single read sequencing. TPM (Transcript Per Million)
RPKM is normalize the sequence depth firstly, and then do the gene length standardization; TPM is normalize the gene length firstly, and then do the sequence depth standardization.
FPKM is the default method in RNA seq analysis, we can’t offer RPKM results. If customer need TPM results, please note and charge additional 12-15 USD/sample. Customer can use NovoMagic After-sales platform to convert read counts to TPM.
The number of sequencing reads is affected by gene length and sequencing depth. We need to do the normalization:
Calculate the total number of reads: calculate the total number of reads of each RNA-seq sample, and then convert it into millions of reads
(M) ;
Normalize the read number of genes (eliminate sequencing depth): the read number of all genes divide by the total reads ;
Normalize the gene length (eliminated gene length): the normalize result divided by the gene length (gene length unit is Kb);
- Can data from strand-specific and non-strand libraries be analyzed together? A: No, data from these two library types can’t be analyzed together. The data of polyA enrichment library and rRNA removal library can’t be analyzed together.
Are we able to do RNA denovo analysis for prokaryotic species?
- A: We are unable to do RNA denovo analysis for prokaryotic and virus. RNA denovo analysis applies to eukaryotic species only.
QuantificationStandard AnalysisData QC√√Mapping√√Gene expression quantification√√Novel gene prediction—√(Except for human & mouse)SNP/InDel/AS—√Differential gene expression√√GO/KEGG/GSEA/PPI enrichment√√DO/Reactome/DisGeNETHuman & MouseHuman & MouseOncogeneHuman & MouseHuman & MouseFusion Gene—Human & Mouse Tumor and Cancer cell linesQuantificationStandard AnalysisData QC√√Mapping√√Gene expression quantification√√Novel gene prediction—√(Except for human & mouse)SNP/InDel/AS—√Differential gene expression√√GO/KEGG/GSEA/PPI enrichment√√DO/Reactome/DisGeNETHuman & MouseHuman & MouseOncogeneHuman & MouseHuman & MouseFusion Gene—Human & Mouse Tumor and Cancer cell linesWhat are the differences between Quantification and Standard analysis package? A:
Quantification
Standard Analysis
Data QC
√
Mapping
√
Gene expression quantification
√
Novel gene prediction
—
√
(Except for human & mouse)
SNP/InDel/AS
—
√
Differential gene expression
√
GO/KEGG/GSEA/PPI enrichment
√
DO/Reactome/DisGeNET
Human & Mouse
Oncogene
Human & Mouse
Fusion Gene
—
Human & Mouse Tumor and Cancer cell lines
Quantification
Standard Analysis
Data QC
√
Mapping
√
Gene expression quantification
√
Novel gene prediction
—
√
(Except for human & mouse)
SNP/InDel/AS
—
√
Differential gene expression
√
GO/KEGG/GSEA/PPI enrichment
√
DO/Reactome/DisGeNET
Human & Mouse
Oncogene
Human & Mouse
Fusion Gene
—
Human & Mouse Tumor and Cancer cell lines
What’s the analysis pipeline for PDX (Patient-derived tumor xenograft, PDX) sample？
A：We have two standard analysis workflows: workflow B and workflow C. After differential expression analysis, we will do function analysis follow mRNA standard analysis (medical-human or mouse) process. Please let client to choose on and give note to Project Manager.
Do we guarantee the RNA extraction result?
- A: We will try our best for RNA extraction. Due to the RNA quality is highly impact by the sample original quality and shipment conditions, we can’t guarantee if the RNA extraction result is good enough for the library prep.
- How to ship tissue samples from overseas?
- A: Please contact logistics team about shipment when you have tissue samples extraction inquiries. All the tissues samples should be instant frozen by liquid nitrogen and shipped with dry ice.
Does Novogene offer RNA Ambient tube (25 tubes/package) for RNA shipping at ambient temperature?
- A: Yes, we have RNA Ambient tube to provide stability for RNA samples in ambient temperature during transportation, eliminating the need to store them in freezers or even ship them on dry ice. For more detail information please contact product manager.
- How long can Novomagic's project data be saved for?
- A: The project data stored in Novomagic is not fastq raw data, it’s some files and data for analysis. Currently, all project data in Novomagic can be used permanently.
What are the functions of NovoMagic platform?
- A: NovoMagic is an after-sales analysis cloud platform independently developed by Novogene. For CSS users, NovoMagic can help you re-analyze and customize your sequencing data. NovoMagic can support you to select specific group of genes, analyze gene expression, identify differential expressed gene and perform gene function analysis.
Who can use NovoMagic?
NovoMagic is free to all customers with a CSS account who have used our Human mRNA and Plant & Animal mRNA sequencing (and have engaged us for bioinformatic services) since 20th June 2022.
Analysis Content
NovoMagic enables the selection of gene groups, the analysis of gene expression, the identification of differentially expressed genes, and gene function analysis with 17 customizable toolkits available.
Re-analysis of exist project*
Customized analysis result (17 toolkits)
Rename sample
Rename sample name
Merge tables
Table split
Table filtering
Convert readcount to FPKM/TPM 5.Correlation analysis
6.Volcano plot 7.PCA
Clustering
Box plot
Adjust parameters for DEG
Venn diagram
Flower plot 13.Heatmap
Violin plot
GO enrichment
KEGG enrichment
Bar plot
Gene filtering
Filter genes by keyword, like KEGG_ID
Filter genes by gene information, like gene_ID
Gene expression analysis
Sample correlation PCA
Venn diagram
DEG analysis
DEG identification
DEG clustering(heatmap) DEG venn diagram
Gene function analysis
GO enrichment KEGG enrichment GSEA
DO enrichment (human & mouse)
Reactome pathway enrichment (human & mouse) DisGeNET enrichment (human & mouse)
NovoMagic is unable to do Data QC, Mapping, SNP/InDel analysis, Novo gene prediction, Fusion gene analysis, PPI analysis. NovoMagic is unable to combine data from two projects.
.
Meta-transcriptome Sequencing
Meta-transcriptome refers to the total content of gene transcripts (RNA copies of the genes) in a nature community (i.e. soil, water, sea, feces, and gut), considered as a unique entity, at a specific moment of sampling. Meta-transcriptome changes with time and environmental variation. Meta-transcriptome sequencing using the next-generation sequencing (NGS) can now be applied to obtain the whole expression profile in a community and to follow the dynamics of gene expression patterns over time or environmental parameters, improving our understanding of the structure, function, and adaptive mechanisms in complex communities.
Meta-transcriptome sequencing identifies gene expression of microbes, both eukaryotes and prokaryotes, within natural environments. Specifically, this service allows you to obtain whole gene expression profiling of complex microbial communities, taxonomic analysis of species, functional enrichment analysis of differently expressed genes, and more.
RNA Extraction (SG Outsource)
Sample types
Recommend Input
Transportation
Soil
Collect soil sample in soil preservation solution, e.g. Qiagen LifeGuard Soil Preservation solution.
Weigh 2 g of soil/sludge sample in 15 ml screw cap tube
Add 5 ml of soil/sludge preservation solution
Vortex or invert tube by hand until the entire soil/sludge sample and preservation solution are mixed well. Excess preservation solution should be sitting on top of the soil sample.
Store sample in 4°C for overnight, transfer to -20°C freezer on the next day.
No. of replicates: 2
Dry Ice
- Note: Please provide more information for evaluation: sample amount, sample pictures, sample preservation solution and so on.
## Sample Requirements
Sample Type
Remarks
Amount
RIN
Volume
Concentration
Purity
(NanoDropTM/Agarose gel)
Total RNA sample
Strongly Recommended
≥ 1 μg
≥ 5.8
≥ 20 μL
≥ 25 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 500 ng
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
Meta-transcriptome library
NovaSeq PE150
12 Gb
18-20 working days
35 working days
Analysis Contents
Standard Analysis
Software
Data Quality Control: filtering reads containing adapter or with low quality
fastp
Statistics Analysis of Data Production and Quality
-
Remove host sequence (Analyze when selecting host)
Bowtie2
De novo Assembly
Trinity+Corset
Gene Functional Annotation (GO,eggNOG, KEGG, CAZy annotation)
Diamond/hmmscan
Taxonomic Analysis
Diamond/MetaStats
Gene Expression Analysis
RSEM
Differential Expression Analysis (two or more groups of samples)
DEGSeq/DESeq /edgeR
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
GOSeq,topGO,hmmscan
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
KOBAS
Comparative Analysis between Various Samples (3 or more samples, including eggNOG/COG functional comparisons, cluster analysis and PCoA analysis)
-
Protein Protein Interaction Analysis of differentially expressed coding genes
BLAST
## FAQ
- What is the library type and library size of meta-transcriptome library?
- A: The library is 250-300bp insert size non-directional library with rRNA removal as default.
If clients want directional library, please add additional charge of 20 USD per sample, please remark library type in quotation and give notice to Project Manager.
- How to do rRNA removal for meta-transcriptome samples?
- A: We will remove both eukaryotic and prokaryotic rRNA. If the species is clearly animal or plant, the ribosome of prokaryotic + animal or prokaryotic + plant will be removed.
If the species is unclear, the ribosomes of prokaryotic + animal + plant will all be removed.
What are the differences between meta-transcriptome and dual RNA seq? A:
Meta-transcriptome
Dual RNA-seq
Sample type
Multiple species from environment
Two species
(host and pathogen)
Reference genome
Without reference genome
With reference genome
Analysis method
Assemble
Alignment
Analysis content
Taxonomic analysis of complex microbial communities
Host-pathogen interaction initiates gene expression changes
Dual RNA sequencing
Dual species transcriptomic experiments allow multiple organisms to be simultaneously analyzed from within the same sample, such as host and bacterial transcripts during an infection. Dual RNA-seq simultaneously profiles the transcriptomes of a host and of a pathogen during infection and may reveal the mechanisms underlying host–pathogen interactions.
## Sample Requirements
Sample Type
Library Type
Remarks
Amount
RIN
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
Total RNA from eukaryotic infected by
eukaryotic
Eukaryotic directional mRNA
library
Strongly Recommended
≥ 800 ng
≥ 5.8 (animals/ plants & fungi/blood)
≥ 20 μL
≥ 20 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 400 ng
Total RNA from eukaryotic infected by
bacteria
Dual RNA seq library
Strongly Recommended
≥ 1.6 μg
≥ 6.5
≥ 20 μL
≥ 50 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 800 ng
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
Dual RNA seq library
NovaSeq PE150
12-15 Gb
18-20 working days
35 working days
Analysis Contents
## FAQ
- What is the library type of dual RNA seq library?
- A: If the species are both eukaryotic, we suggest mRNA non-directional/ directional library, sample requirement please refer to mRNA non-directional/ directional library;
If the species are eukaryotic (host) and prokaryotic (pathogen), we suggest doing dual RNA directional library with rRNA removal.
- How much data is recommended for dual RNA seq?
- A: We strongly recommend 12-15Gb data, if pathogen species have small portion, we suggest more than 15Gb. Please remark the species (example: bacterial + plant or bacterial + animal) in your quotation.
Appendix 1 Special Requirement Evaluation Form for CAP lab
（一）The Application for Special Requirement
Department
AMEA
Applicant
Date of Application
Purpose
Special requirement details
Expected result
Expected Completion date
Remarks
（二）评估结果(Lab evaluation results)
评估结果反馈
评估人
评估日期
承诺完成时间
（三）签字确认(Signature)
需求部门负责人
日期
评估部门负责人
日期
Appendix 2 Price of Customized /After-sale Analysis
Analysis
Price
TAT
Remark
PM instructions
QC + mapping
60% of Quantification
analysis price
Quantification TAT
Change Threshold: Diff
+Enrichment
60% of Quantification analysis price
Quantification TAT
No change in sample name/grouping methods/reference
genome
Modify parameter/Change software of differential
analysis
Add or change comparison
groups: Diff + Enrichment
60% of Quantification
analysis price
Quantification TAT
Venn diagram is
included
Add or change comparison groups: AS+ Diff+ Enrichment
60% of Standard analysis price
Standard TAT
In standard analysis, alterative splice is based on comparison groups
Coexpression Venn/ Differential expression Venn
10 USD/Figure (< 5 figures)
8 USD/Figure (> 5 figures)
2 days/5 Figures
Email BI for details: Coexpression venn/Differential expressed venn/UP or DOWN differential
expressed venn
Cluster Analysis (Heatmap)
10 USD/Figure (< 5 figures)
8 USD/Figure (> 5 figures)
2 days/5 Figures
Email BI for details: Clustering method (according to sample or biological replicate or comparison group or group in venn or
provide gene list)
A variety of grouping methods in BIF (Multi-column groups)
If there are more than 3 grouping methods, each additional one will be charged 100 USD. (Each
group, every 6 samples)
2 days/additional group
TPM
12-15 USD /sample
4 days (no more than 30 samples)
Results: gene_tpm.xls, gene_tpm_group.xls,
violin, bloxplot, density.
WGCNA
The analysis with 15-50 samples will be charged 120 USD/project
4 days when the number of samples is less than 50. 2 more days for every 25
additional samples.
Novogene Product Manual
Non-coding RNA Sequencing
AMEA 2023.06
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclose to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
Novogene Product Manual – non-coding RNA Sequencing
Revision Number
2023 V1.0
Issue Date
June 2023
Prepared by
Tianran Shi
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Pg 5 – Add RNA extraction sample requirement of plant and bacteria Pg 6 – Exosome lncRNA TAT and note update
Pg 8 – FAQ2 Exosome total RNA extraction kit suggestion Pg 10 –Exosome small RNA TAT and note update
Pg 14 –FAQ4 piRNA analysis unit price Pg 14 –FAQ5 siRNA analysis unit price
Tianran Shi
June 2023
Contents
LncRNA Sequencing5
RNA Extraction (Outsource)5
## Sample Requirements6
Sequencing Strategy and Turnaround Time6
Analysis Contents7
## FAQ7
Small RNA Sequencing10
Sample requirements10
Sequencing Strategy and Turnaround Time10
Analysis Contents11
## FAQ13
Circular RNA Sequencing15
Sample requirements15
Sequencing Strategy and Turnaround Time15
Analysis Contents15
## FAQ16
Whole Transcriptome Sequencing18
Sample requirements18
Sequencing Strategy and Turnaround Time18
Analysis Contents19
Package 1 (LncRNA+ small RNA)19
Package 2 (LncRNA+ small RNA+ circRNA)21
## FAQ24
LncRNA Sequencing
Long non-coding RNA sequencing service (lncRNA-seq) is a comprehensive next-generation method to detect the transcripts with a length of over 200nt, which do not encode protein and perform as regulatory elements in multiple biological processes. However, the progressive library preparation enables information enrichment and gene expression profiling for both coding and non-coding transcripts from a high-sensitive transcriptomic perspective. Bioinformatic analysis does not reveal the quantification and functional enrichment of the target transcripts, but also indicates the strand orientation and regulatory relation of lncRNA targeted mRNA.
RNA Extraction (Outsource)
Sample types
Recommend Input
Transportation
Human Blood
≥ 3mL in TempusTM Blood RNA Tubes
fresh sample only Storage at 4°C fridge
Blood samples to be submitted immediately after withdrawal
Results will not be guaranteed for blood samples that are more than 3 days old 3 replicates per sample to be sent
Follow tube specification
Tissue sample (Human or Animal)
Tissue must be wash with 1X PBS to remove all traces of blood Weight: 30mg
Snap Frozen in liquid nitrogen after 1XPBS wash and weighing. Store in -80°C freezer
3 replicates per sample to be sent
Dry Ice
Plant
Young leaves/needles Weight: 100mg
Snap frozen in liquid nitrogen Store in -80°C freezer
3 replicates per sample to be sent
Dry Ice
Cultured Cells
Pellet form 1 x 107
Storage in -80°C freezer
3 replicates per sample to be sent
Dry Ice
Bacteria
Pellet form (30ml of overnight culture) Storage in -80°C freezer
3 replicates per sample to be sent
Dry Ice
- Note: Please provide more information for evaluation: sample amount, sample pictures, sample preservation solution and so on.
## Sample Requirements
Sample Type
Remarks
Amount
RIN
Volume
Concentration
Purity
(NanoDropTM/Agarose gel)
Total RNA sample
Strongly Recommended
≥ 1 μg
≥ 5.5 (animals)/ 5.5 (plants & fungi)
≥ 20 μL
≥ 25 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 500 ng
Total RNA sample from isolated exosome*
Strongly
Recommended
≥ 10 ng
Peak Range: 80-200 nt, FU≥ 10, without peak ≥ 2000nt (by high sensitive Agilent
Bioanalyzer 2100）
≥ 10 μL
≥ 1 ng/μL
Required
≥ 5 ng
- Note:
* Please refer to FAQ.
Sequencing Strategy and Turnaround Time
Service
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
LncRNA
NovaSeq PE150
Minimum: 10Gb/ sample; Recommendation: 15Gb/ sample
WOBI
WBI
15-18 working days
25-30 working days
Exosome LncRNA
NovaSeq PE150
Recommendation: 12Gb/ sample
45 working days*
60 working days*
- Note: *Please note the TAT of exosome lncRNA seq in you quotation additionally. The default TAT in your quotation is for normal lncRNA seq when you quote exosome lncRNA.
Analysis Contents
Long noncoding RNA Sequencing-Standard Analysis (LncRNA) Exosome Long noncoding RNA Sequencing-Standard Analysis (Exosome lncRNA)
Software
Data Quality Control: filtering reads containing adapter or of low quality
Fastp
Statistics of Data Production and Quality
Mapping to Reference Genome
HISAT2
Transcriptome Variation Analysis
Alternative Splicing Analysis SNP/InDel Calling
rMATS GATK
lncRNA Identification
Stringtie
Novel Gene Prediction
gffcompare
lncRNA Target Prediction
Quantification
Stringtie-eb
Correlation Analysis (for samples with biological replicates only)
Differential Expression Analysis (for two or more groups)
edgeR
Enrichment Analysis of differentially expressed coding genes and lncRNA targets
GO Enrichment
KEGG Pathway Enrichment
clusterProfiler
Network Analysis of Protein-protein interaction for differentially expressed coding genes and lncRNA targets
diamond blastx
## FAQ
- What is the library size for Long non-coding RNA library (exosome Long non-coding RNA library)? A: 250-300bp insert directional library with rRNA removal.
- What is the sample requirement about exosome RNA?
- A: Total RNA must be extracted from isolated exosome. Before exosomes are isolated, no RNA protective reagent (such as Trizol, RNA later) can be added.
Sample type: Serum, plasma, seminal plasma, cell supernatant and so on. Please contact product manager for other sample types.
We suggest using commercialized kit (exoRNeasy Serum/Plasma Maxi Kit (Qiagen) or miRNeasy Serum/Plasma Kit (Qiagen) or miRNeasy Serum/Plasma Advanced Kit), Ultracentrifugation or density gradient centrifugation to enrich exosomes.
Why cultured cells use two rRNA removal kits?
- A: We will remove both eukaryotic and prokaryotic rRNA due to the bacterial contamination always exists in the culture media. So please note the cultured cells sample type to project manager.
Does lncRNA analysis can cover mRNA analysis contents?
- A: Yes, it does. LncRNA standard analysis have differential gene expression and enrichment analysis in both transcript and gene level.
Do we need to remove the Globin mRNA in human blood sample? What is the difference between Globin clear and Globin zero?
- A: Globin mRNA accounted for more than 76% of the total mRNA. Therefore, if globin mRNA and ribosomal RNA are not completely removed, the analysis of low abundance transcripts will be seriously affected. We suggest customer to remove Globin mRNA for blood mRNA sequencing. Customers can also choose to remove it or not.
Globin clear - GlOBINclearTM Kit (Thermo Fisher, Catalog number: AM1980, 20 preps)
The GlOBINclearTM—Human Kit uses a novel, non-enzymatic technology that rapidly depletes >95% of the alpha and beta globin mRNA
from total RNA preparation derived from whole blood. Novogene only offers human GlOBINclearTM Kit now.
Globin Zero - TruSeq Stranded Total RNA with Ribo-Zero Globin (Illumina, 48 preps or 96 preps) Simultaneous removal of rRNA and globin mRNA while retaining the mRNA and noncoding RNA population.
The goal of this kit is to wash and resuspend magnetic beads, which then bind to removal probes hybridized to rRNA and globin mRNA, producing an RNA sample ready for library prep.
This kit couples the benefits of Ribo-Zero ribosomal RNA reduction chemistry with RNA sequencing (RNA-Seq) technology for whole-transcriptome analysis of human, mouse or rat samples.
Human blood RNA sample requirement is same with LncRNA library preparation requirement. Please contact with Product manager if you have human blood samples enquiry for reagent stock.
- Can we guarantee the RNA extraction result?
- A: We will try our best for RNA extraction. Due to the RNA quality is highly impact by the sample original quality and shipment conditions, we can’t guarantee if the RNA extraction result is good enough for the library prep.
- How to ship tissue samples from overseas?
- A: Please contact Product Manager and logistics team about shipment when you have tissue samples extraction inquiries. All the tissues samples should be instant frozen by liquid nitrogen and shipped with dry ice.
Small RNA Sequencing
Novogene offers comprehensive Small RNA Sequencing service (sRNA-seq), to investigate the regulatory network of noncoding RNA of 18-40nt in length, especially for microRNA (miRNA) transcripts. Variations in miRNA can be correlated with gene silencing and post-transcriptional regulation of gene expression, which provides researchers an effective method of regulating target on mRNAs with unprecedented sensitivity and high resolution. Bioinformatic analysis of sRNA-seq illustrates differential expression of miRNAs, structural alterations and discovery of novel small RNAs via a high throughput research technique.
Sample requirements
Sample Type
Remarks
Amount
RIN
Volume
Concentration
Purity
(NanoDropTM/Agarose gel)
Total RNA sample
Strongly
Recommended
≥ 4 μg
≥ 7.5(animals) / 7(plants & fungi)
≥ 20 μL
≥ 50 ng/μL
OD260/280 > 2.0
OD260/230 ≥ 2.0
No degradation or DNA contamination
Required
≥ 2 μg
Total RNA sample from isolated exosome*
Strongly Recommended
≥ 20 ng
Peak Range: 25-200 nt (by highly sensitive Agilent 2100 Bioanalyzer), FU≥ 10, with no
peak >2000nt
≥ 20 μL
≥ 1 ng/μL
Required
≥ 10 ng
- Note: * Please refer to FAQ.
Sequencing Strategy and Turnaround Time
Service
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
Small RNA
18-40 bp insert sRNA library
NovaSeq SE50
Minimum: 10M reads/ sample Recommendation: 20M reads/ sample
20-22 working days
25-30 working days
Exosome
Small RNA
18-45 bp insert
sRNA library
NovaSeq SE50
Recommendation: 10M reads/ sample
30 working
days*
40 working days*
- Note: *Please note the TAT of exosome lncRNA seq in you quotation additionally. The default TAT in your quotation is for normal lncRNA seq when you quote exosome lncRNA.
Analysis Contents
Small RNA Sequencing-Standard Analysis (miRNA) Exosome Small RNA Sequencing-Standard Analysis (Exosome miRNA)
Software
Data Quality Control: filtering reads containing adapter or of low quality
-
Summary of the Length Distribution
-
Common and Specific Sequences among samples
-
Mapping to Reference Genome
Bowtie
Identification of Known miRNA
miREvo, Mirdeep
Identification of rRNA, tRNA, snRNA, snoRNA and non-coding RNA
Bowtie
Identification of Repeat Associated small RNAs
RepeatMasker
Alignment of small RNA to mRNA, exon and intron
Bowtie
Prediction of Novel miRNAs and Secondary Structure Detection from unannotated small RNAs
miREvo, Mirdeep, ViennaRNA
Expression Pattern of known miRNAs
-
Base Bias of miRNAs
-
Classification and Annotation
-
Correlation analysis (for samples with biological replicates only)
-
Differential Expression and Cluster Analysis (for two or more groups)
DEseq2
Prediction of miRNA target genes
Animal: miRanda/RNAhybrid
Plant: psRobot
Enrichment Analysis of differentially expressed miRNA target genes
GO Enrichment
KEGG Pathway Enrichment
clusterProfiler
- Note: Advanced analysis includes but not limited to following contents. Standard analysis is required when client wants to order advanced or personalized analysis, please add on standard analysis price and TAT when you quote.
Advanced Analysis- piRNA
Data Quality Control: Filtering reads containing adapter or uncertain nucleotides or of low quality, and statistic summary of data quality
Summary of Length Distribution
Mapping Clean Reads to Reference Genome
piRNA Analysis
Identification of piRNA
miRNA Base Bias Analysis
Quantification Analysis
Chromosome Distribution Analysis
Source Gene Analysis
Functional Enrichment Analysis
piRNA Cluster Analysis
Quantification Analysis
Chromosome Distribution Analysis
Differential Expression Analysis
Adjacent Gene Analysis
Advanced Analysis - siRNA
Software
Data Quality Control: Filtering reads containing adapter or uncertain nucleotides or of low quality, and
statistic summary of data quality
Summary of Length Distribution
Sequence Assembly
PFOR, velvet
Contig Classification and Annotation
Mapping Clean Reads to Reference (Host Genome, Nr Database, NT Database, Virus RefSeq Database)
BLAST
Summary of Virus Species Candidate
## FAQ
- What is the sample requirement about exosome RNA?
- A: Total RNA must be extracted from isolated exosome. Before exosomes are isolated, no RNA protective reagent (such as Trizol, RNA later) can be added.
Sample type: Serum, plasma, seminal plasma, cell supernatant and so on. Please contact Product manager for other sample types. For plasma and PBMC samples we strongly recommend doing exosome small RNA instead of small RNA seq.
We suggest using commercialized kit ((exoRNeasy Serum/Plasma Maxi Kit (Qiagen) or miRNeasy Serum/Plasma Kit (Qiagen) or miRNeasy Serum/Plasma Advanced Kit), Ultracentrifugation or density gradient centrifugation to enrich exosomes.
What are the features of exosome?
- A: 1) The fragment distribution is small, mainly in the range of 25 ~ 200nt;
2) Different from normal tissues and cells, small RNA accounts for a high proportion in exosomes.
What are the species experiences of small RNA?
- A: Species experiences of sRNA project: For animals we can accept mammals and poultry, and for plants we can accept soybean, tomato (callus), medlar, potato, watermelon, Camellia oleifera, apple, grape, pineapple, banana (don’t accept fruit), Kiwi (don’t accept fruit), Arabidopsis, upland cotton, Phyllostachys pubescens, Rhodococcus, alfalfa, orchid, chrysanthemum, Chinese fir, poplar, pea and duckweed. The above plant samples are roots and seeds.
We don’t accept bacteria species for small RNA-seq.
sRNA 项目物种经验:动物可接哺乳动物和家禽，植物可做物种有大豆、番茄(愈伤组织)、枸杞、马铃薯、 西瓜、油茶、苹果、葡萄、凤梨、香蕉(果实不接)、猕猴桃(果实不接)、拟南芥、陆地棉、雷竹、红球藻、 苜蓿、兰花、菊花、杉木、杨树、豌豆、鸭茅草。上述植物取样为根和种子.
What are the species experience of piRNA?
- A: The species that can do piRNA analysis include Human, Mouse, Drosophila melanogaster, Zebrafish. Other species please ask APM team to evaluate. The piRNA analysis must base on the standard small RNA analysis. Unit price of piRNA analysis: 60% of small RNA standard analysis unit price.
What kind of species can do siRNA analysis?
- A: siRNA database only can analyze viral siRNA infected animal or plant. The siRNA analysis must base on the standard small RNA analysis. Unit price of siRNA analysis: 60% of small RNA standard analysis unit price.
Circular RNA Sequencing
Circular RNA (circRNA) is a highly stable molecule of ncRNA, in form of a covalently closed loop that lacks the 5’end caps and the 3’ poly(A) tails. The circular structure grants to circRNAs resistance against exonuclease digestion, a characteristic that can be exploited in library construction.
Sample requirements
Sample Type
Remarks
Amount
RIN
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
Total RNA sample
Strongly Recommended
≥ 2 μg
≥ 7(animals) 6.5(plants & fungi)
≥ 20 μL
≥ 50 ng/μL
OD260/280 > 2.0
OD260/230 ≥ 2.0,
No degradation or DNA contamination
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
circRNA library
NovaSeq PE150
Minimum: 30M reads per sample (9Gb) Recommendation: 40M reads per sample (12Gb)
25 working days
40 working days
Analysis Contents
Standard Analysis- circRNA
Software
Data Quality Control: filtering reads containing adapter or low quality
Fastp
Statistics of Data Production and Quality
Mapping to Reference Genome
HISAT2
circRNA Identification
find_circ,CIRI
Quantification
Correlation analysis (for samples with biological replicates only)
Differential Expression Analysis (for two or more groups)
DESeq2(with biological replicates),edgeR(without biological
replicates )
Enrichment Analysis of the Source Genes of differentially expressed circRNAs
GO Enrichment
KEGG Pathway Enrichment
clusterProfiler
miRNA Binding Site Prediction
miRanda
Prediction of CircRNA coding potential
IRES/CPC/CNCI/pfam_scan
## FAQ
- How to do circRNA library?
- A: Firstly, remove rRNA with ribosome removal kit, then enrich circRNA by removing linear RNA with RNase R to construct directional library.
- How many lncRNA data are circRNA data?
- A: Around 10%, it is related to the sample type and state of cells, because the expression of circRNA has tissue specificity and timing, and the expression amount of circRNA is different in cells or tissues from different sample types and states.
- What is the species experience of Novogene on circRNA seq?
- A: Human, rat, mouse, pig, sheep, cattle, chicken, rabbit, tree shrew, birds, chicken, zebrafish, tilapia, grass carp, Paralichthys olivaceus, rice, tobacco, cotton, plum blossom, upland cotton, two spike short tail grass, watermelon, pear, kelp, Eucommia ulmoides, fungi and grapes.
(人，大鼠，小鼠，猪，绵羊，耗牛，牛，鸡、兔子，树鼩，鸟类，鸡，斑马鱼，罗非鱼，草鱼，牙鲆，水稻，烟草，棉花，梅花，陆地棉，二穗短尾草，西瓜，梨，海带，杜仲，真菌、葡萄)
Whole Transcriptome Sequencing
Novogene’s Whole Transcriptome Sequencing service equips the researcher with cutting-edge NGS solutions that provide in-depth bioinformatic analysis on all transcripts including mRNAs and non-coding RNAs. This competitive approach investigates and explores potential transcriptional and regulatory network mechanisms, while providing key insights into interaction and intersection functionality from a comprehensive transcriptomic perspective.
Sample requirements
Library Type
Remarks
Amount
RIN
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
LncRNA library & sRNA library
Strongly Recommended
≥ 5 μg
≥ 7.5(animals)/
7.0 (plants & fungi)
≥ 30 μL
≥ 50 ng/μL
OD260/280 =1.8-2.2
OD260/230 ≥ 2.0,
No degradation or DNA contamination
Required
≥ 2.5 μg
ncRNA library & sRNA library &
Strongly Recommended
≥ 9 μg
≥ 50 μL
≥ 50 ng/μL
circRNA
Required
≥ 4.5 μg
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Package1: LncRNA library & sRNA
library
NovaSeq PE150 & NovaSeq SE50
≥ 40M reads per sample (lncRNA library);
≥ 20M reads per sample (small RNA library);
Package2: LncRNA library & sRNA library & circRNA
NovaSeq PE150 & NovaSeq SE50 & NovaSeq PE150
≥ 40M reads per sample (lncRNA library);
≥ 20M reads per sample (small RNA library);
≥ 40M reads per sample (circRNA library);
Analysis Contents
Package 1 (LncRNA+ small RNA)
Long noncoding RNA Sequencing-Standard Analysis (LncRNA)
Software
Data Quality Control: filtering reads containing adapter or of low quality
Fastp
Statistics of Data Production and Quality
Mapping to Reference Genome
HISAT2
Transcriptome Variation Analysis Alternative Splicing Analysis SNP/InDel Calling
rMATS GATK
lncRNA Identification
Stringtie
Novel Gene Prediction
gffcompare
lncRNA Target Prediction
Quantification
Stringtie-eb
Correlation Analysis (for samples with biological replicates only)
Differential Expression Analysis (for two or more groups)
edgeR
Enrichment Analysis of differentially expressed coding genes and lncRNA targets
GO Enrichment
KEGG Pathway Enrichment
clusterProfiler
Network Analysis of Protein-protein interaction for differentially expressed coding genes and lncRNA targets
diamond blastx
Small RNA Sequencing-Standard Analysis (sRNA)
Software
Data Quality Control: filtering reads containing adapter or of low quality
-
Summary of the Length Distribution
-
Common and Specific Sequences among samples
-
Mapping to Reference Genome
Bowtie
Identification of Known miRNA
miREvo
Identification of rRNA, tRNA, snRNA, snoRNA and non-coding RNA
-
Identification of Repeat Associated small RNAs
RepeatMasker
Alignment of small RNA to mRNA, exon and intron
-
Prediction of Novel miRNAs and Secondary Structure Detection from unannotated small RNAs
Mirdeep, Vienna
Expression Pattern of known miRNAs
-
Base Bias of miRNAs
-
Classification and Annotation
-
Correlation analysis (for samples with biological replicates only)
-
Differential Expression and Cluster Analysis (for two or more groups)
-
Prediction of miRNA target genes
miRanda/psRobot
Enrichment Analysis of differentially expressed miRNA target genes
GO Enrichment
KEGG Pathway Enrichment
GOSeq,topGO,hmmscanKOBAS
Correlation Analysis between lncRNA and miRNA
(RNA-seq for corresponding samples is needed simultaneously.) *
Conjunction Analysis of Differentially Expressed mRNA and Differentially Expressed miRNA Targeting genes
Targeting Relation Analysis
GO Enrichment Analysis
KEGG Enrichment Analysis
Regulation Network Analysis of miRNA and its target mRNA
Conjunction Analysis of Differentially Expressed mRNA, Differentially Expressed miRNA Targeting genes and Differentially Expressed lncRNA Targeting genes
Interaction Analysis of lncRNA targets and mRNA
Homology analysis of lncRNA and pre-miRNA
Targeting Relation Analysis of lncRNA and miRNA
Regulatory networks of lncRNA, miRNA, and mRNA
Package 2 (LncRNA+ small RNA+ circRNA)
Long noncoding RNA Sequencing-Standard Analysis (LncRNA)
Software
Data Quality Control: filtering reads containing adapter or of low quality
Fastp
Statistics of Data Production and Quality
Mapping to Reference Genome
HISAT2
Transcriptome Variation Analysis Alternative Splicing Analysis
SNP/InDel Calling
rMATS GATK
lncRNA Identification
Stringtie
Novel Gene Prediction
gffcompare
lncRNA Target Prediction
Quantification
Stringtie-eb
Correlation Analysis (for samples with biological replicates only)
Differential Expression Analysis (for two or more groups)
edgeR
Enrichment Analysis of differentially expressed coding genes and lncRNA targets
GO Enrichment
KEGG Pathway Enrichment
clusterProfiler
Network Analysis of Protein-protein interaction for differentially expressed coding genes and lncRNA targets
diamond blastx
Small RNA Sequencing-Standard Analysis (sRNA)
Software
Data Quality Control: filtering reads containing adapter or of low quality
-
Summary of the Length Distribution
-
Common and Specific Sequences among samples
-
Mapping to Reference Genome
Bowtie
Identification of Known miRNA
miREvo
Identification of rRNA, tRNA, snRNA, snoRNA and non-coding RNA
-
Identification of Repeat Associated small RNAs
RepeatMasker
Alignment of small RNA to mRNA, exon and intron
-
Prediction of Novel miRNAs and Secondary Structure Detection from unannotated small RNAs
Mirdeep, Vienna
Expression Pattern of known miRNAs
-
Base Bias of miRNAs
-
Classification and Annotation
-
Correlation analysis (for samples with biological replicates only)
-
Differential Expression and Cluster Analysis (for two or more groups)
-
Prediction of miRNA target genes
miRanda/psRobot
Enrichment Analysis of differentially expressed miRNA target genes
GO Enrichment
KEGG Pathway Enrichment
GOSeq,topGO,hmmscanKOBAS
Circular RNA Standard Analysis- circRNA
Software
Data Quality Control: filtering reads containing adapter or low quality
Fastp
Statistics of Data Production and Quality
Mapping to Reference Genome
HISAT2
circRNA Identification
find_circ,CIRI
Quantification
Correlation analysis (for samples with biological replicates only)
Differential Expression Analysis (for two or more groups)
DESeq2(with biological replicates),edgeR(without biological replicates )
Enrichment Analysis of the Source Genes of differentially expressed circRNAs
GO Enrichment
KEGG Pathway Enrichment
clusterProfiler
miRNA Binding Site Prediction
miRanda
Prediction of CircRNA coding potential
IRES/CPC/CNCI/pfam_scan
Correlation Analysis between lncRNA, miRNA and circRNA (RNA-seq for corresponding samples is needed simultaneously.) *
Conjunction Analysis of Differentially Expressed mRNA and Differentially Expressed miRNA Targeting genes
Targeting Relation Analysis
GO Enrichment Analysis
KEGG Enrichment Analysis
Regulation Network Analysis of miRNA and its target mRNA
Interaction Analysis of lncRNA targets and mRNA
Conjunction Analysis of Differentially Expressed mRNA, Differentially Expressed miRNA Targeting genes and Differentially Expressed lncRNA Targeting genes
Homology analysis of lncRNA and pre-miRNA
Targeting Relation Analysis of lncRNA and miRNA
Regulatory networks of lncRNA, miRNA, and mRNA
Conjunction Analysis of Differentially Expressed mRNA, Differentially Expressed miRNA Targeting genes and Differentially Expressed circRNA Source genes
Interaction Analysis of circRNA and its source gene
Targeting Relation Analysis Regulation
Network Analysis of circRNA, miRNA and mRNA
- Note:
*Please refer to FAQ.
## FAQ
Do we need do LncRNA/ sRNA/ circRNA standard analysis before doing whole transcriptome sequencing analysis?
- A: Whole transcriptome sequencing analysis package1 includes lncRNA standard analysis, small RNA standard analysis, interaction of lncRNA and miRNA, interaction of mRNA and miRNA, regulatory network of lncRNA, miRNA and mRNA.
Whole transcriptome sequencing analysis package2 includes lncRNA standard analysis, small RNA standard analysis, circRNA standard analysis, interaction of lncRNA and miRNA, interaction of mRNA and miRNA, interaction of circRNA and miRNA, regulatory network of lncRNA, miRNA and mRNA and regulatory network of circRNA, miRNA and mRNA.
Normally, customer can choose lncRNA+sRNA. Price bases on the price list.
If customer wants to do lncRNA+sRNA+circRNA, please check with Product Manager about the species experience and price.
- Can we use lncRNA data to analyze circRNA?
- A: LncRNA may analyze some circRNA information but can’t analyze the complete circRNAs. If the customer pays more attention on circRNA, it is strongly recommended to do circRNA library preparation and standard analysis instead of using lncRNA data to analyze circRNA.
- What is ceRNA?
- A: ceRNA network is a hypothesis, the cross-talk between RNAs through microRNA response elements (MREs) could form a large-scale regulatory network across the transcriptome, including both coding and non-coding RNAs. Like other ceRNAs namely pseudogenes, lncRNAs and circRNAs, mRNAs also contain MREs, which are normally located within the 3′UTR. All of these RNAs potentially compete for miRNA binding, thereby regulating miRNA repression. Thus, mRNAs, different types of ceRNAs and miRNAs would form a network of interactions, as called ceRNA network. ceRNAs usually contain carry MREs for multiple miRNAs, each miRNA can regulate multiple ceRNAs and most ceRNAs are regulated by more than one miRNA.
What species experience do we have now?
- A: Current experience: Homo_sapiens, Mus_musculus. We can try to analyze other species but unable to guarantee the results.
Novogene Product Manual
Human Whole Genome Sequencing
AMEA 2024.11
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director.
If you have any questions about the products, please consult the APM team.)
Product Manual Revisions
Subject
Novogene Product Manual-4 Human WGS AMEA Product Manual- 2024 V1.0
Revision Number
2024 V1.0
Issue Date
Nov 30th, 2024
Prepared by
Chen Yu
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Pg 4-Tube recommendation up for saliva samples for DNA extraction Pg 5-Sample Requirements Updated
Pg 6-NovaSeq X Plus sequencing depth recommendation added
Pg 7-Cancer Advanced Analysis: removed Tumor Neoantigen Identification. Pg 10-FAQ 1: Sample Questions for customers
Pg 12-FAQ 8: PCR products sample requirements Pg 14-FAQ 9: DNBSeq experience update
Pg 18-FAQ 18-19: VAF customized analysis Pg 19-FAQ 20: LOH customized analysis
Pg 20-FAQ 21: HLA cost update to 45 USD/sample
Chen Yu
June 29th, 2023
2024 V1.0
Pg 5-DNA Extraction Update
Pg 6-Sample Requirement Update
Pg 7-Standard Analysis Content Update
Pg 8-Advanced Analysis Content (Cancer) Update Pg 11-FAQ 1: Example Questions
Pg 12-FAQ 2: Library size for hWGS Pg 13-FAQ 5: cfDNA extraction
Pg 14-FAQ 8: hWGS PCRproducts update
Chen Yu
Nov 30th, 2024
Pg 15-FAQ 9: Sequencing on DNBseq
Pg 16-FAQ 13: PON database for DNBseq Pg 16-FAQ 14: mtDNA analysis
Contents
Human Whole Genome Sequencing5
DNA extraction5
## Sample Requirements of Human whole genome (PCR) library6
## Sample Requirements of PCR-Free library6
Sequencing Strategy and Turnaround Time7
Analysis Contents7
Demo for data release structure10
## FAQ11
Human Whole Genome Sequencing
Human whole genome sequencing (hWGS) enables researchers to catalog genetic constitution of individuals and capture all variants present in a single assay. It is utilized to study cancer and a variety of diseases, as well as human population evolution studies and pharmacogenomics.
DNA extraction
Sample type*
Species
Recommended
input**
Replicates
Tube recommendations
Transportation
Whole Blood
Human
≥ 1 ml
2
EDTA Tube
Follow Tube
specification
PBMC
Human
≥0.5 ml
2
Sterile, Pre-cooled 1.5/2.0 mL
EP Tube
Follow Tube
specification
Buccal Swabs/ Tongue
Swab/ Mouth/ Cheek
Human
≥ 4
2
Sterile, Pre-cooled 1.5/2.0 mL
EP Tube
Dry Ice
Saliva
Human
≥ 4 ml
2
Oragene DNA (DNA Genotek)
Collection tube
Ice Bag
Buffy coats***
Human
≥ 200 ul
3
1.5ml Eppendorf tube
Dry ice
Cell pellets
cell lines from any
species
5-10*106 cells
3
1.5ml Eppendorf tube
Dry ice
FFPE Tissue Sections****
Human/Mouse/Rat
10 sections, 5um
thick (or tissue area:250mm2)
3
Slide box
Ice bag
FFPE Tissue Scrolls****
Human/Mouse/Rat
2-3 scrolls sections,
30um thick (or tissue area: 250mm2)
3
Slide box
Ice bag
FFPE Tissue Blocks****
Human/Mouse/Rat
2 blocks, 2mm diameter
3
Slide box
Ice bag
- Note:
All DNA extractions will be conducted in our Singapore facility. For projects involving a larger sample volume, please consult the APM team in advance to confirm kit availability before proceeding with sample collection.
** If any samples do not meet our DNA extraction requirements, kindly submit an inquiry to the APM team for further evaluation and guidance
*** Buffy coat DNA extraction will be conducted using the same process as whole blood DNA extraction. Please refer to the price list for further details when preparing a quote.
**** FFPE DNA extraction is only available in China and requires proper shipping arrangements for these samples. An additional charge of $100 USD per sample will apply for working with FFPE DNA as the starting material for library preparation and sequencing, even if Novogene performs the DNA extraction.
## Sample Requirements of Human whole genome (PCR) library
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (NanoDropTM/Agarose Gel)
Human whole genome library
Genomic DNA
≥ 100ng
≥ 20 μL
≥ 5 ng/μL
OD260/280 = 1.8-2.0, no degradation, no contamination
FFPE* DNA
≥ 400ng
≥ 20 μL
≥ 15 ng/μL
Fragments should be longer than 1500 bp
- Note:
For more information on our experience with FFPE DNA and the additional costs associated with library preparation and sequencing, please refer to FAQ 3.
## Sample Requirements of PCR-Free library
Type
Amount
Volume
Concentration
Purity (NanoDropTM/Agarose
Remark
(Qubit®)
Gel)
PCR-Free library (Genomic DNA)
≥ 1.2 μg
≥ 20 μL
≥ 50 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination
Magnetic beads were used for segment selection and the
recovery rate was about 80%
PCR-Free library (PCR product*)
≥ 1.5 μg
≥ 20 μL
≥ 60 ng/μL
Without segment, Select by gel-cutting, with recovery rate of about 20%
- Note:
For detailed information on PCR product requirements, please refer to FAQ 8. If the PCR product exceeds 500 bp, we recommend fragmenting it to a size range of 100–500 bp, with an ideal target library size of approximately 350 bp. Clearly indicate the PCR product size in the quotation to inform the PM team.
Please note that human PCR-free libraries with a 500 bp insert size are not accepted as starting material for PCR product samples.
During the pre-sales process, ensure that the client’s PCR product is free of adapters and sequencing primers, as their presence can disrupt sequencing and result in data generation failure.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 30 samples)
Normal Sample
Tumor Sample
WOBI
WBI
Human whole genome library
NovaSeq PE150
30×
50×
15 working days
22 working days
Analysis Contents
Human WGS Standard Analysis
Software
Data quality control: filtering reads containing adapter or with low quality
Alignment to reference genome; statistics of sequencing depth and coverage
BWA, Sambamba
Germline variant (SNP, InDel, CNV, and SV) calling, annotation and statistics
Display of Genomic Variants with Circos
GATK (SNP, InDel), Delly (SV), Control-freec (CNV), Annovar
(annotation), Circos
Somatic variant detection (only apply for tumor-normal paired samples)
-SNP calling, annotation and statistics
-InDel calling, annotation and statistics
-CNV calling, annotation and statistics
-SV calling, annotation and statistics
MuTect (SNP) Strelka (InDel) Control-freec (CNV) Delly (SV)
Annovar (annotation)
- Note:
Advanced analysis encompasses, but is not limited to, the following services. Please note that standard analysis is a prerequisite for ordering advanced or customized analyses. Ensure that the standard analysis cost and turnaround time (TAT) are included in the quotation.
The prices, TAT, and requirements listed below pertain exclusively to advanced analysis services.
Application Field
Content of Advanced Analysis
Price (USD)
TAT
(d)
Requirement
Cancer
Screening for Predisposing Genes (for normal samples only)
15/sample
2
Mutational Spectrum & Mutational Signature
120/project
3
≥20 paired samples
Driver gene analysis
Identification of Known Driver Genes
15/pair samples
2
Paired samples
Significantly Mutated Gene & Pathway Analysis
75/project
3
≥20 paired samples
Mutation Relation Test of Significantly Mutated Genes
75/project
2
≥20 paired samples
Identification of Driver Genes Based on Mutation Clustering Bias
75/project
3
≥20 paired samples
Identification of Driver Somatic CNVs
75/project
3
≥20 paired samples
Identification of Driver Mutations in Noncoding Regions
75/project
2
Paired samples
Mutation Site Displaying
75/project
2
≥20 paired samples
Tumor heterogeneity analysis
Tumor Purity & Ploidy Estimation
15/pair samples
3
Paired samples
Intra-tumor Heterogeneity Analysis
15/pair samples
3
Paired samples
Tumor Evolution Analysis (One normal and at least 3 tumor samples from the same patient are needed)
75/project
3
Paired samples, Tumor samples ≥ 3
Fusion Gene Detection
30/pair samples
3
Paired samples
Tumor Mutation Burden Analysis (TMB)
280 / 50 pairs samples
3
Paired samples
Application Field
Content of Advanced Analysis
Price (USD)
TAT(d)
Requirement
Disease
Candidate Variant Filtration
60/project
2
Analysis under dominant/ recessive model
60/family
2
Linkage Analysis
60/family
2
Family based
Region of Homozygosity Analysis (ROH)
60/family
2
Family based
De novo SNV/INDEL Analysis
60/family
2
Family based (Trio/Quartet)
ACMG classification for variants
30/sample
2
Candidate CNV/SV Filtration
30/sample
2
Application Field
Content of Advanced Analysis
Price (USD)
TAT(d)
Requirement
Personalized analysis & (Cancer Disease)
HLA typing
45/sample
3
Just for normal
samples
CRISPR/Cas9 Off-target Analysis
75/pair samples
8
case/control paired samples; gRNA sequence is
required
Xenograft Tumor Analysis
30/sample
4
Integration Site Detection
60/sample
6
Exogenous
sequence required
Somatic SNP/InDel detection for Single-Tumor sample
45/sample
4
Demo for data release structure WOBI:
WBI:
Standard Unpaired (Germline)
03.Variant and Annotation03.Variant and Annotation
03.Variant and Annotation
03.Variant and Annotation03.Variant and AnnotationStandard Paired (Germline + Somatic)
03.Variant and Annotation
## FAQ
What questions should you ask upon receiving a human whole genome sequencing (hWGS) inquiry? A: Please refer to the table below for sample questions to guide new hWGS inquiries.
Question Types
Questions to Ask the Customer
Follow-up Clarification Questions
Possible Solutions
Q1.1 Do they require DNA extraction?
A1.1 Please refer to the DNA extraction sample requirements.
A1.2 Additional charges apply for working with FFPE DNA, cfDNA, and ctDNA. (100 USD/sample)
A1.3 Please submit an inquiry to the APM with with details of the pretreatment for evaluation.
A1.4 Proceed to Q2.
Yes, to A1.1; No, to Q1.2.
Q1. What kind of sample is the
Q1.2 Are the DNA samples from FFPE
customer working with?
DNA, cf/ctDNA? Yes, to A1.2; No, to A1.4.
Q1.3 Have the samples undergone any
pretreatment? Yes, to A1.3; No, to A1.4.
A2.1 Somatic analysis can proceed, as
paired samples are required. A minimum of
Project-based Questions.
Q2. Are they working with a tumor-based samples?
Yes, to Q2.1; No, to Q3.
Q2.1 Can they provide paired normal and tumor samples? Yes, to A2.1; No, to A2.2.
one normal sample is needed for paired analysis.
A2.2 Somatic analysis cannot proceed.
Please confirm with the customer whether
they would like to proceed with personalized
analysis instead.
A3.1 Advanced analysis details can be found
Q3. Are they working with normal or diseased samples?
Yes, to Q3.1; no to Q3.2.
Q3. Does the customer require advanced analysis? Yes; to A3.1; No to A3.2.
Q3.2 Are the samples unique or require specialized analysis? Yes; to A3.3; No to A3.2.
in our analysis content and FAQs.
A3.2 Please proceed with our standard WOBI or BI project.
A3.3 Personalized analysis details are
available in our analysis content, or you may submit an inquiry to the APM for customized
analysis evaluation.
- What is the library size for a human whole-genome library?
- A: Our standard library size is ~350bp for both PCR library and PCR-free library. However, please note that 350bp is a range, and not an exact value. During the library preparation, we implement a strict quality management process to ensure the library size remains within the range of 320-350 bp. Variations in sample quality and reagent batches may cause slight differences in insert size between batches. Such variations are normal and do not impact data quality or the accuracy of downstream analysis.
- How is the minimum sample requirement for performing human whole-genome sequencing (WGS) with FFPE DNA?
- A: FFPE stands for Formalin-Fixed, Paraffin-Embedded. The minimum recommended sample amount for FFPE DNA is more than 200 ng (based on experience), with a fragment length greater than 300 bp. However, please note that library preparation in such cases is considered high-risk, and we cannot guarantee the results. It is essential to inform the client of these risks before proceeding with the offer. Only SNP/InDel calling analysis will be provided for FFPE DNA samples.
An additional charge of $100 USD per sample will apply for library preparation when working with FFPE DNA or FFPE samples.
What are the sample requirements for cfDNA/ ctDNA?
- A: The total cfDNA/ctDNA amount should be greater than 40 ng, with a concentration exceeding 1 ng/μL and a volume of at least 20 μL. The sample should exhibit a peak at 170 bp, with integer multiples observed in 2100 testing, and must be free from genomic (gDNA) contamination.
- Can we perform cfDNA extraction?
- A: We no longer are able to perform cfDNA extraction. For any customer requests related to cfDNA extraction, please submit an inquiry for a case-by-case evaluation.
If the client sends us cfDNA/ ctDNA sample, will there be any additional charge for this kind of sample type? A: Yes, please charge an additional 100USD per sample.
Are there other options for different library sizes besides our standard library insert size? A: We offer the following insert size libraries at no additional charge:
100-500bp, 100-350bp, 200-300bp, 200-400bp, 500bp.
Please note that PCR-free libraries cannot accommodate a 500 bp insert size for PCR products. For custom insert sizes or additional charges, kindly contact the APM team.
- What is the special notice for PCR product as the start material? A: Please see the chart below for more information:
Starting Sample Type
Contain any adapters,
sequencing primers or sequencing
indexes?
Insert size (bp)
Solutions
Remarks
Products in SFDC
PCR
products
Yes
100-490
The customer is required to provide samples as pre-made libraries.
The customer is responsible for completing the library preparation and providing us with the samples as pre-made libraries.
Using PCR products for library preparation may lead to issues with sequencing
data output.
RSSQ00503 Pre-made libraries partial lane sequencing (NovaSeq PE150): RSSQ00203 Pre-made libraries partial lane sequencing (NovaSeq PE250)
≥ 500
Inquiry needed
No
≤ 100
We cannot accept libraries with an insert size smaller than 100 bp for preparation.
100-490
Novogene prepares a standard PCR-free library for each individual PCR product.
RSHD01203 Human PCR
Product Whole Genome Sequencing (WOBI);
≥ 500
The customer is required to provide 1.5 µg of PCR product. Novogene will fragment the
PCR product and perform standard PCR-free library preparation for each individual PCR product.
RSHD01213 Human PCR
Product Whole Genome Sequencing (WBI)
- Can we provide DNBSEQ platform for Human WGS?
- A: Yes, we offer DNBSEQ-T7 sequencing services for hWGS.
The sample requirements and recommended sequencing depth are consistent with those of the Illumina NovaSeq platform. For detailed pricing information, please refer to the price list.
What kind of sample/ library type can’t be operated on DNBSEQ platform?
- A: The DNBSEQ platform cannot process FFPE DNA samples or cfDNA/ctDNA samples.
If clients want to merge SNP/ InDel VCF for different samples, can we offer this service?
- A: Yes, the fee for merging SNP and InDel VCF files for fewer than 20 samples is 60 USD per case.
If SNP and InDel VCF merging includes annotation results, the charge is 120 USD per case for fewer than 20 samples. For CNV merging, please contact the APM team for case-by-case evaluation.
As this is a customized analysis request, please ensure that the 'Customized Analysis Note' is included in the quotation to inform the PM team.
Are we able to provide somatic variant analysis for unpaired tumor samples?
- A: Yes, we can perform somatic variant analysis for unpaired tumor samples using the Panel of Normal (PON) database from GATK.
Analysis cost*：
Somatic SNP/InDel: 45 USD per sample
Analysis Content (with PON database):
SNP/InDel calling, annotation, and statistics. Somatic SNP/InDel calling, annotation, and statistics.
Additional TAT*: 3 working days above standard product TAT
- Note:
*All the above information is for SNP/InDel analysis only, not including standard analysis. Will require standard analysis price and TAT.
- How to quote this analysis in SFDC system?
Choose customized analysis process, and remark it in the customized analysis note when quoting the project
Are we able to use the PON database for samples sequenced on other platforms such as MGI-DNBSeq T7? A: Yes, we can use the PON database for samples sequenced on other platforms, such as MGI-DNBseq.
This is possible because we have updated our PON database from Novogene's curated version to the GATK PON database. Please refer to FAQ 12 for pricing information.
For more PON information, please refer to the following link: https://gatk.broadinstitute.org/hc/en-us/articles/360035890631-Panel-of-Normals-PON
- Can we perform mitochondrial DNA analysis using human WGS technology? If so, what is the recommended sequencing depth and cost? A: Yes, we can perform mitochondrial DNA analysis using human WGS data. Please note that this is an untargeted approach.
Based on our testing, 5x human WGS (15 Gb) data provides an average mitochondrial DNA coverage depth of approximately 400-600x. For higher coverage, we recommend using 30x human WGS, which results in an average mitochondrial DNA coverage depth of around 5000x.
Analysis Cost*:
SNP/InDel: 80-90 USD per sample;
SV/CNV (if required): 50-60 USD per sample on top of SNP/InDel cost
Analysis content (mitochondrial DNA analysis) *:
Data quality control: filtering reads containing adapter or with low quality. Alignment to the reference genome; statistics of sequencing depth and coverage. SNP/InDel calling, annotation, and statistics.
SV/CNV calling, annotation, and statistics (if required).
Additional TAT*: 4-5 working days per 50 samples above standard product TAT.
Delivery content*:
Raw data(fq);
Analysis result: bam, vcf, annotation if requires data analysis; Project report for SNP/InDel analysis;
Project report for SV/CNV analysis (if required).
- Note:
*All the above information is for Mitochondrial DNA analysis only, not including standard analysis. Standard analysis is not a required analysis.
- How to quote this analysis in SFDC system?
Choose customized analysis process, and remark it in the customized analysis note when quoting the project
- Can we offer low-pass whole genome sequencing? What is the recommended sequencing depth for studying SNP and InDel mutations? A: Yes, we can offer low-pass WGS. The library preparation and sequencing process are the same as for standard WGS. Recommended sequencing depth: 4-10x.
Minimum sample number: 20 and above Reference version: hg19 only
Special requirement: Library preparation and sequencing for this request will be performed only at our Tianjin lab.
Analysis Cost*:
100-120USD per sample
Analysis content (low pass human WGS) *:
Data quality control: filtering reads containing adapters or with low quality
Alignment to the reference genome; statistics of sequencing depth and coverage
SNP/InDel calling, annotation, and statistics (joint calling)
CNV calling, annotation, and statistics (if required) (SV analysis is not recommended).
Additional TAT*: 18-20 working days per 100 samples above standard product TAT.
Delivery content*:
Raw data(fq).
Analysis result: bam, vcf, gVCF, annotation if requires data analysis. Project report for SNP/InDel analysis
Project report for CNV analysis (if required).
- Note:
*The above information pertains specifically to low-pass whole-genome sequencing analysis and does not include standard analysis.
- How to quote this analysis in SFDC system?
Choose customized analysis process, and remark it in the customized analysis note when quoting the project.
- Can we offer common variation and unique variation (SNP/InDel) calling between different samples? A: Yes, we can offer common variation and unique variations among samples (SNP/InDel).
Analysis Cost *:
60 USD per case within 20 samples
Additional TAT*: 1 working day per 50 samples above standard product TAT
- Note:
*All the above information is for this customized analysis, not including standard analysis. Standard analysis is also required.
- Can we offer common variation and unique variation (SNP/InDel) calling between different groups? A: Yes, we can offer common variation and unique variation among groups (SNP/InDel).
Analysis workflow:
Standard analysis for each sample.
Common variations calling (1) for Group A, common variations calling (2) for Group B, common variations calling (3) for Group C……
Comparison: same SNP/InDel between (1) and (2) are common variations between group A and B. Same with Group A and C, or Group B and C. If (1) have variation A but (2) don’t have, then it is unique variation for Group A. Same rules for Group B unique variations and other Groups.
All the results will deliver by sample level. Each sample will have common and unique variations results, including SNP/InDel calling and annotation.
- Note:
If the sample number is big, the client needs to choose the cut-off value for step 2-common variants calling for groups.
Additional price and TAT:Need evaluation case by case.
Are we able to provide variant allele frequency (VAF) results as a customized analysis? A: Yes, we can provide VAF results for SNP and InDel as part of the release.
Sample required:
Tumor/ Normal paired samples, as VAF is based on somatic standard analysis.
Additional Analysis Cost*:
SNP/InDel: 55-60 USD per case (for up to 20 samples)
Analysis Content (only VAF):
VAF SNP/InDel calling, annotation and statistics.
Additional TAT*: 2 working days per 50 samples above standard product TAT.
Delivery content*:
Analysis result: bam, vcf, annotation if requires data analysis;
- Note:
*All the above information is for VAF analysis only, not including standard analysis. Somatic standard analysis is a required analysis.
- How to quote with this analysis in SFDC system?
Choose customized analysis process, and remark it in the customized analysis note when quoting the project.
- What is the purpose of the VAF analysis?
- A: VAF is a surrogate measure of the proportion of DNA molecules in the original specimen carrying a specific variant. VAF can be used for our advanced cancer analyses, tumor purity and ploidy, and intra-tumor heterogeneity analysis.
- Can we provide loss of heterozygosity (LOH) analysis? A: Yes, we can provide LOH analysis.
Sample required:
Tumor/ Normal paired samples, as it is based on somatic standard analysis.
Additional Analysis Cost*:
SNP/InDel: 25-30 USD per sample
Analysis Content (LOH)：
LOH results
Additional TAT*: 2 working days per 24 samples above standard product TAT.
Delivery content*:
Excel document.
- Note:
*All the above information is for LOH analysis only, not including standard analysis. Somatic standard analysis is a required analysis.
- How to quote with this analysis in SFDC system?
Choose customized analysis process, and remark it in the customized analysis note when quoting the project.
- Can we provide HLA typing for MHC class II for our HLA typing analysis?
- A: Our standard HLA typing, as described in the product manual, is performed using PolySolver software, which provides HLA typing for MHC Class I only. If the customer requires HLA typing for both MHC Class I and II, we can offer this analysis using HLA-HD software. The cost for HLA-HD typing analysis is $45 USD per sample.
Since this is a customized analysis, please include a remark in the quotation to inform the Project Manager (PM).
Do we have any customized analysis available if the customer is looking to study the relationship between a specific disease and genes?
- A: Yes, our DisGenNet analysis provides gene-disease association analysis on relevant genes and variants for a disease that is picked from a list of diseases by the customer. Please reach out to the APM team for this list of diseases. Please note that the results provided will be research-based and not clinical-based.
Sample required:
Disease or Trio samples
Additional Analysis Cost*:
100 USD/ case, within 20 samples
Analysis Content：
DisGenNet Annotation results and Phenolyzer Analysis Results
Additional TAT*: 2 working days per 24 samples above standard product TAT.
Delivery content*:
Excel document
- Note:
*All the above information is for this customized analysis only, not including standard analysis. Standard analysis is a required analysis.
- How to quote this analysis in SFDC system?
Choose customized analysis process, and remark it in the customized analysis note when quoting the project.
Novogene Product Manual
Whole Exome Sequencing
AMEA 2024.12
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director.
If you have any questions about the products, please consult the APM team.)
Product Manual Revisions
Subject
Novogene Product Manual-5 Whole Exome Sequencing AMEA Product Manual- 2024 V1.0
Revision Number
2024 V1.0
Issue Date
Dec 19th, 2024
Prepared by
Chen Yu
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Pg 4-Panels Positioning: Agilent V8 TAT to 20 wk days
Pg 9-Turnaround Time for Agilent V8: 30 wk days to 20 wk days (WOBI)
35 wk days to 25 wk days (WBI)
Pg 11-Cancer Advanced Analysis: Removed Tumor Neoantigen Identification. Instead, we can provide Neoantigen Prediction. Please refer to FAQ 35 on pg. 29.
Pg 18-FAQ9: minimum sample requirement per batch for V8 removed Pg 25-FAQ 30-31: Addition of VAF customized analysis
Pg 26-FAQ 32：Addition of LOH customized analysis
Pg 27-FAQ 34: Addition of DisGenNet customized analysis
Pg 29-FAQ 35: Neoantigen Prediction price update to 330-350 USD/ sample set
Chen Yu
March 15th, 2023
2024 V1.0
Pg 5-Panels Positioning update Pg 6-WES Battle Card update
Pg 8-(Human WES): DNA extraction update
Chen Yu
Dec 19th, 2024
Pg 9-(Human WES); Sample requirements update
Pg 11-(Human WES): Standard analysis content update Pg 16-(Human WES) FAQ 1: Example Questions
Pg 19-(Human WES) FAQ 8: Starting materials for Twist Exome 2.0
Pg 20-(Human WES) FAQ 9: Minimum sample requirements for Twist Exome 2.0 Pg 20-(Human WES) FAQ 10: Starting materials for Agilent SureSelect V8
Pg 20-(Human WES) FAQ 11: Minimum batch requirements for Agilent SureSelect V8 Pg 20-(Human WES) FAQ 12: Differences between Agilent V6 and Agilent V8
Pg 21-(Human WES) FAQ 15: WES with customer requested kits Pg 23-(Human WES) FAQ 16: WES with DNBSEQ
Pg 24-(Human WES) FAQ 22: Differences between coverage and sequencing depth Pg 26-(Human WES) FAQ 27: PON database update
Pg 26-(Human WES) FAQ 28: PON database with DNBSEQ update Pg 29-(Human WES) FAQ 32: LOH analysis update
Pg 32-(Human WES) FAQ 35: Neoantigen prediction analysis update Pg 34-(Mouse WES): Sample requirements update
Pg 34-(Mouse WES): Standard analysis content update
Pg 37-(Mouse WES) FAQ 2: Minimum batch requirements update Pg 37-(Mouse WES) FAQ 3: FFPE samples
Pg 37-(Mouse WES) FAQ 5: Other organisms with mouse WES kit
Contents
WES PANELS POSITIONING5
Panel Positioning5
WES Human Battle Card6
HUMAN WHOLE EXOME SEQUENCING8
DNA EXTRACTION8
## Sample Requirements of Human WES9
Sequencing Strategy and Turnaround Time10
Analysis Contents11
Demo for data release structure14
## FAQ16
MOUSE WHOLE EXOME SEQUENCING34
## Sample Requirements34
Sequencing Strategy and Turnaround Time34
Analysis Contents34
Demo for data release structure35
## FAQ37
APPENDIX 1 SPECIAL REQUIREMENT EVALUATION FORM FOR CAP LAB38
WES Panels Positioning
Panel Positioning
Positioning
Fastest TAT (< 2 weeks)
Most cost- effective package
Most comprehensive /up-to-date database & Analysis
Mouse Exome
Customer profile
I need consistency and fast TAT.
I need validation of data results.
I need the best price
I need versatility and experiences with different sample types.
I am new to WES or cross-over from another
product type.
I need the best and most-up-to-date coverage of genes.
I would like to upgrade from Agilent V7.
I need to study mouse samples for human-related research
Suggested probes
IDT xGEN Hybridization Panel
Agilent SureSelect V6
Agilent SureSelect V8
Twist Exome 2.0
1. Agilent SureSelectXT Mouse
WOBI TAT*
(~24 samples)
10 working days
18 working days
V8-20 working days Twist 2.0-30 working days
30 working days
Sample type
IDT (CAP/CLIA compliant): gDNA from blood, saliva, cell lines/pellets
V6 (CAP/CLIA Compliant) gDNA from blood, saliva, cell lines/pellets. FFPE
V6:
gDNA from blood, saliva, cell lines/pellets, FFPE, and other tissues, as well as cfDNA/ctDNA
V8:**
gDNA from blood, saliva, cell lines/pellets, FFPE
Twist 2.0: ***
gDNA from blood, saliva, cell lines/pellets
Mouse: **
gDNA from mouse, FFPE
Price
+++
++
+++
- Note:
* The turnaround time (TAT) for WBI projects may vary if there is a change in the sample number, especially for projects with more than 24 samples.
** Both the Agilent SureSelect V8 and Agilent SureSelectXT Mouse kits have a minimum sample requirement. An additional charge of 80 USD per sample will apply if the minimum sample number is not met.
*** For the TWIST 2.0 kit, samples must be submitted in multiples of 8 per batch. Samples that do not meet this requirement will not be accepted.
WES Human Battle Card
Human WES Battle Card
Agilent SureSelect Human All Exon
V6
Agilent SureSelect Human All Exon
V8
Twist Exome 2.0
Release date
2016
2021
Target size
60M
35.1M
36.5M
Probe size
58M
41.6M
43.2M
Fold_80
2.32
1.58
1.50
Accepted sample type
gDNA from blood, saliva, cell lines/pellets, other tissues, FFPE as
well as cfDNA/ctDNA*.
gDNA from blood, saliva, cell lines/pellets, FFPE
gDNA from blood, saliva, cell lines/pellets
Coding region
Database
CCDS, RefSeq, GENCODE
CDS Release 22, RefSeq Release 95,
GENCODE V31
CCDS32, RefSeq38, GENCODE35,
Clinvar, HCMG73, ENSEMBLv101**
Additional Spike-Ins
N/A***
Benefits
Widely accepted WES panel
Best price and TAT compared to the newer options (V8 and Exome 2.0)
Experienced with various sample
types.
Updated coding databases
More targeted probe size
Better fold_80 than V6
Better performance than V7
Updated coding databases
Includes noncoding databases
More targeted probe size
Disadvantages
Older coding databases
Higher dup ratio than V6
Need to check reagent stock
Additional spike-ins require evaluation.
Not as widely accepted as Agilent’s panels
Need to check reagent stock
Additional spike-ins require evaluations
Which customers do we target?
Existing customers who are comfortable with V6 WES.
Customers who have been using V7 probe.
Suitable for customers who wish to subsequently convert WES assay to Clinical assay (LDT) from their
research work. ****
Notes:
* For cfDNA/ctDNA, please see FAQ for more information.
** Twist Exome 2.0 includes noncoding databases: Clinvar, HCMG73, and ENSEMBLv101, alongside coding databases.
*** We currently have no experience in using spike-ins for both Agilent SureSelect V8 and Twist Exome 2.0 and this will require evaluation. Please see FAQ for more information.
**** We do not offer clinical assay (LDT) services for the customer. Instead, this is to highlight the additional databases available within Twist Exome 2.0 that are more clinical-orientated.
Human Whole Exome Sequencing
Exome sequencing offers a cost-effective alternative to whole-genome sequencing by targeting the protein-coding regions of the human or mouse genome, which are responsible for the majority of known disease-related variants. At present, human and mouse species can be analyzed through whole exome sequencing (WES) as commercial probe kits are available for capture and library construction. However, species lacking commercial probe kits cannot be analyzed using WES.
DNA extraction
Sample Types*
Species
Recommended
Input**
Replicates
Tube Recommendation
Transportation
Whole Blood
Human
≥ 1 ml
2
EDTA Tube
Follow Tube
specification
PBMC
Human
≥ 0.5 ml
2
Sterile, pre-cooled 1.5/ 2.0ml
EP Tube
Follow Tube
Specification
Saliva
Human
≥ 4 ml
2
Oragene DNA (DNA Genotek)
Collection tube
Ice Bag
Buccal Swabs/Tongue
Swab/ Mouth/ Cheek
Human
≥ 4
2
Sterile, pre-cooled 1.5/ 2.0 ml
EP Tube
Dry Ice
Buffy Coats***
Human
≥ 200 ul
3
1.5 ml Eppendorf Tube
Dry Ice
Cell Pellets
Cell lines from any
species
5-10X106cells
3
1.5 ml Eppendorf Tube
Dry Ice
FFPE tissue sections****
Human/Mouse/Rat
10 sections, 5 µm
thick (Tissue area: 250mm2)
3
Slide Box
Dry Ice
FFPE tissue scrolls****
Human/Mouse/Rat
2-3 scrolls sections, 30 µm thick (Tissue
area: 250mm2)
3
Slide Box
Dry Ice
FFPE tissue block****
Human/Mouse/Rat
2 blocks, 2 mm
diameter
3
Slide Box
Dry Ice
- Note:
All DNA extractions will be conducted in our Singapore facility. For projects involving a larger sample volume, please consult the APM team in advance to confirm kit availability before proceeding with sample collection.
** If any samples do not meet our DNA extraction requirements, kindly submit an inquiry to the APM team for further evaluation and guidance
*** Buffy coat DNA extraction will be conducted using the same process as whole blood DNA extraction. Please refer to the price list for further details when preparing a quote.
**** FFPE DNA extraction is only available in China and requires proper shipping arrangements for these samples. An additional charge of $100 USD per sample will apply for working with FFPE DNA as the starting material for library preparation and sequencing, even if Novogene performs the DNA extraction.
## Sample Requirements of Human WES
Library Type*
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/Agarose Gel)
Strongly Recommended
Required
Human Exome Library
(Agilent V6 60M)
Genomic DNA
≥ 600 ng
≥ 300 ng
≥ 20 μL
≥ 15 ng/μL
OD260/280 = 1.8 – 2.0,
no degradation, no contamination
FFPE** DNA
≥ 1.0 μg
≥ 400 ng
≥ 20 μL
≥ 15 ng/μL
Fragments should be longer than 1000 bp
cfDNA** / ctDNA
≥ 60 ng
≥ 40 ng
≥ 20 μL
≥ 1 ng/μL
Fragments should be in multiples of 170 bp, no genomic contamination
Human Exome Library
(IDT 51M)
Genomic DNA
≥ 1 μg
≥ 500 ng
≥ 15 μL
≥ 20 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination
Human Exome Library
(Agilent V8 41.6M)
***
Genomic DNA
≥ 600 ng
≥ 300 ng
≥ 20 μL
≥ 15 ng/μL
OD260/280 = 1.8 – 2.0,
no degradation, no contamination
Human Exome Library
(TWIST 2.0 43.2M)
****
Genomic DNA
≥ 600 ng
≥ 300 ng
≥ 20 μL
≥ 15 ng/μL
OD260/280 = 1.8 – 2.0,
no degradation, no contamination
- Note:
Size of capture probes
** Please refer to FAQs 2-4 for the additional charges and detailed information.
*** Multiples of 4 samples per batch are required for Agilent V8 kit and an additional 80 USD/sample will apply sample number does not fulfill.
**** Multiples of 8 samples per batch are required for TWIST 2.0 kit and we do not accept the samples if the samples do not meet this requirement.
Sequencing Strategy and Turnaround Time
Library Type
Library Preparation Kit
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 24 samples)
WOBI
WBI
Human Exome Library
Agilent SureSelect Human All Exon V6 (60M)
NovaSeq PE150
For normal and Mendelian disorder/complex disease: ≥ 50×(6Gb) *
For tumor sample: ≥
100×(12Gb) **
18 working days
22 working days
Human Exome
Library
IDT xGen® Exome Research
Panel (51M)
NovaSeq PE150
10Gb data per sample*
10 working days
15 working days
Human Exome
Library
Agilent SureSelect Human All
Exon V8 (41.6M)
Novaseq PE150
For normal: 50X(6Gb)
For tumor: 100X (12Gb)
20 working days
25 working days
Human Exome Library
TWIST Exome 2.0 (43.2 M)
Novaseq PE150
For normal and tumor: 100X(10G) and 200x(20G)
For disease: 50-100X(5-10G) for
frequent variants and 200x (20G) for rare variants
30 working days
35 working days
- Note:
Agilent V6: Please note that the 50X (6Gb) option is not available through the CAP lab. The CAP lab exclusively offers 12Gb and 24Gb options for Agilent V6.
** IDT xGEN Panel: This panel is available only through the CAP lab, with a fixed data output of 10Gb. For additional details, please refer to the FAQ.
Analysis Contents
Standard Analysis
Software
Data quality control: filtering reads containing adapters or with low quality
fastp
Alignment with reference, statistics of sequencing depth, and coverage
BWA, Sambamba
Germline SNP and InDel calling, annotation, and statistics
GATK, ANNOVAR
Somatic variant detection (only apply for tumor-normal paired samples)
-SNP calling, annotation, and statistics
-InDel calling, annotation, and statistics
-CNV calling, annotation, and statistics
SNP: MuTect InDel: Strelka CNV: Control-freec
Annotation: ANNOVAR
- Note:
Advanced analysis encompasses, but is not limited to, the following services. Please note that standard analysis is a prerequisite for ordering advanced or customized analyses. Ensure that the standard analysis cost and turnaround time (TAT) are included in the quotation.
The prices, TAT, and requirements listed below pertain exclusively to advanced analysis services.
Application
Field
Content of Advanced Analysis
Price (USD)
TAT (d)
Requirement
Cancer
Screening for Predisposing Genes (for normal samples only)
15/sample
2
Mutational Spectrum & Mutational Signature
120/project
2
≥20 paired samples
Driver gene analysis
Identification of Known Driver Genes
15/pair samples
2
Paired samples
Significantly Mutated Gene & Pathway Analysis
75/project
3
≥20 paired samples
Mutation Relation Test of Significantly Mutated Genes
75/project
2
≥20 paired samples
Identification of Driver Genes Based on Mutation
Clustering Bias
75/project
3
≥20 paired samples
Identification of Driver Somatic CNVs
75/project
3
≥20 paired samples
Mutation Site Displaying
75/project
2
≥20 paired samples
Tumor heterogeneity analysis
Tumor Purity & Ploidy Estimation
15/pair samples
3
Paired samples
Intra-tumor Heterogeneity Analysis
15/pair samples
3
Paired samples
Tumor Evolution Analysis (One normal and at least 3
tumor samples from the same patient are needed)
75/project
3
Paired samples,
Tumor samples ≥ 3
Tumor Mutation Burden Analysis (TMB)
150 / 50 pairs samples
3
Paired samples
Application Field
Content of Advanced Analysis
Price (USD)
TAT(d)
Requirement
Disease
Candidate Variant Filtration
60/project
2
Analysis under dominant／recessive model
60/family
2
Linkage Analysis
60/family
2
Family based
Region of Homozygosity Analysis (ROH)
60/family
2
Family based
De novo SNV/INDEL Analysis
60/family
2
Family based
(Trio/Quartet)
ACMG classification for variants
30/sample
2
Application Field
Content of Advanced Analysis
Price (USD)
TAT(d)
Requirement
Personalized analysis
HLA typing*
45/sample
3
Just for normal samples
(Cancer & Disease)
Xenograft Tumor Analysis
30/sample
4
Somatic SNP/InDel detection for Single-Tumor
sample
45/sample
4
CNV detection for WES Single-Sample
20/sample
3
Just for tumor or disease
samples
- Note:
Please refer to FAQ 33.
Demo for data release structure: WOBI:
03. Variant and Annotation03. Variant and AnnotationWBI:
03. Variant and Annotation
Standard analysis- Unpaired samples:Standard analysis- Unpaired samples:
Standard analysis- Unpaired samples:
WBI:
Standard analysis- Paired samples:
03. Variant and Annotation03. Variant and Annotation
03. Variant and Annotation
## FAQ
Question TypesQuestions to Ask the CustomerFollow-up Clarification QuestionsPossible SolutionsProject-based QuestionsQ1. Has the customer done any WES before?Q1.1 Are they an existing customer? Yes, to A1.1; No, to Q1.2.Q1.2. Does the customer have a preferred company or probe?Yes, to A1.2; No, to Q1.3.Q1.3 Does the customer require CAP validation for their project?Yes, to A1.3; No, to A1.4A1.1 If the customer is an existing client, it is recommended to maintain consistency with their previously used probes or suggest the probe most similar to their prior selection.A1.2 If the customer specifies a company or probe preference that aligns with our offerings, recommend one of our standard probes. If the preferred probe is not available within our offerings, refer to the FAQs for further guidance.A1.3 Novogene offers two probes under the CAP lab certification. Please consult the FAQs for additional details.A1.4 If the customer is new and uncertainabout probe selection, refer to FAQ 2 for guidance.Question TypesQuestions to Ask the CustomerFollow-up Clarification QuestionsPossible SolutionsProject-based QuestionsQ1. Has the customer done any WES before?Q1.1 Are they an existing customer? Yes, to A1.1; No, to Q1.2.Q1.2. Does the customer have a preferred company or probe?Yes, to A1.2; No, to Q1.3.Q1.3 Does the customer require CAP validation for their project?Yes, to A1.3; No, to A1.4A1.1 If the customer is an existing client, it is recommended to maintain consistency with their previously used probes or suggest the probe most similar to their prior selection.A1.2 If the customer specifies a company or probe preference that aligns with our offerings, recommend one of our standard probes. If the preferred probe is not available within our offerings, refer to the FAQs for further guidance.A1.3 Novogene offers two probes under the CAP lab certification. Please consult the FAQs for additional details.A1.4 If the customer is new and uncertainabout probe selection, refer to FAQ 2 for guidance.What questions should you ask upon receiving a huma whole exome sequencing (hWES) inquiry? A: Please refer to the table below for sample questions to guide new hWES inquiries.
Question Types
Questions to Ask the Customer
Follow-up Clarification Questions
Possible Solutions
Project-based Questions
Q1. Has the customer done any WES before?
Q1.1 Are they an existing customer? Yes, to A1.1; No, to Q1.2.
Q1.2. Does the customer have a preferred company or probe?
Yes, to A1.2; No, to Q1.3.
Q1.3 Does the customer require CAP validation for their project?
Yes, to A1.3; No, to A1.4
A1.1 If the customer is an existing client, it is recommended to maintain consistency with their previously used probes or suggest the probe most similar to their prior selection.
A1.2 If the customer specifies a company or probe preference that aligns with our offerings, recommend one of our standard probes. If the preferred probe is not available within our offerings, refer to the FAQs for further guidance.
A1.3 Novogene offers two probes under the CAP lab certification. Please consult the FAQs for additional details.
A1.4 If the customer is new and uncertain
about probe selection, refer to FAQ 2 for guidance.
Question Types
Questions to Ask the Customer
Follow-up Clarification Questions
Possible Solutions
Project-based Questions
Q1. Has the customer done any WES before?
Q1.1 Are they an existing customer? Yes, to A1.1; No, to Q1.2.
Q1.2. Does the customer have a preferred company or probe?
Yes, to A1.2; No, to Q1.3.
Q1.3 Does the customer require CAP validation for their project?
Yes, to A1.3; No, to A1.4
A1.1 If the customer is an existing client, it is recommended to maintain consistency with their previously used probes or suggest the probe most similar to their prior selection.
A1.2 If the customer specifies a company or probe preference that aligns with our offerings, recommend one of our standard probes. If the preferred probe is not available within our offerings, refer to the FAQs for further guidance.
A1.3 Novogene offers two probes under the CAP lab certification. Please consult the FAQs for additional details.
A1.4 If the customer is new and uncertain
about probe selection, refer to FAQ 2 for guidance.
Sample-Based Questions
Q2. What type of samples is the customer working with?
Q2.1 Do they require DNA extraction? Yes, to A2.1; No, to Q2.2.
Q2. Are the DNA samples derived from FFPE, cfDNA, or ctDNA?
Yes, to A2.2; No, to A2.4.
Q2.3 Have the samples undergone any pretreatment?
Yes, to A2.3; No, to A2.4.
A2.1 Please refer to the DNA extraction sample requirements.
A2.2 An additional charge of 80 USD per sample applies for processing FFPE DNA, cfDNA, and ctDNA.
A2.3 Please submit an inquiry to the APM with detailed pretreatment information for an evaluation.
A2.4 Proceed to Q3.
Analysis-Based Questions
Q3. Are they working with a tumor-based samples?
Yes, to Q3.1; No, to Q4.
Q3.1 Can they provide paired normal and tumor samples? Yes, to A3.1; No, to A3.2.
A3.1 Somatic analysis can proceed, as paired samples are required. A minimum of one normal sample is needed for paired analysis.
A3.2 Somatic analysis cannot proceed. Please confirm with the customer whether they would like to proceed with personalized analysis instead.
Q4. Are the samples patient-derived xenograft (PDX) samples?
Yes, to Q4.1; No, to Q5.
Q4.1 Does the customer require us to perform analysis for the PDX samples? Yes, to A4.1; No, to A4.2.
A4.1 If the customer requires analysis and the PDX samples are tumor-based, include the customized analysis "xenograft tumor analysis" in the quote along with the standard analysis.
A4.2. If no analysis is required, please proceed with our standard WOBI project.
Q5. Are they working with normal or diseased samples?
Yes, to Q5.1; no to Q5.2.
Q5. Does the customer require advanced analysis?
Yes; to A5.1; No to A5.2.
Q5.2 Are the samples unique or require specialized analysis?
Yes; to A5.3; No to A52.
A5.1 Advanced analysis details can be found in our analysis content and FAQs.
A5.2 Please proceed with our standard WOBI or BI project.
A5.3 Personalized analysis details are available in our analysis content, or you may submit an inquiry to the APM for customized analysis evaluation.
If a customer has no preference for a specific kit, which kit should we recommend?
- A: In such cases, we recommend the Agilent SureSelect V6 kit from our available options.
- What is the insert size of the Human WES library?
- A: The insert size typically ranges from 180 bp to 280 bp.
What does FFPE stand for, and what is the additional charge for library preparation? A: FFPE stands for Formalin-Fixed, Paraffin-Embedded.
An additional charge of 80 USD per sample applies for library preparation when working with FFPE DNA or FFPE samples.
- What is the sample requirement for cfDNA/ ctDNA?
- A: The total cfDNA/ctDNA amount should be greater than 40 ng, with a concentration exceeding 1 ng/μL and a volume of at least 20 μL. The sample should exhibit a peak at 170 bp, with integer multiples observed in 2100 testing, and must be free from genomic (gDNA) contamination.
- Can cfDNA/ ctDNA be used for WES? What is the additional charge for library preparation?
- A: Yes, cfDNA/ctDNA can be used for WES. However, cfDNA/ctDNA samples are generally of lower quality compared to genomic DNA due to their unique characteristics. For samples with less than 30 ng of cfDNA/ctDNA, we will attempt to proceed with library preparation using the entire sample amount, but this will be done at the customer’s risk. An additional charge of 80 USD per sample applies for library preparation.
What's the buffer that dissolves genomic DNA?
- A: The buffer used for DNA storage includes ddH2O, 10 mM Tris, EB buffer, or 0.1x TE.
What starting materials are accepted for TWIST Exome 2.0?
- A: We currently accept gDNA extracted from blood, saliva, cell lines/pellets, and other tissues samples.
For cfDNA/ctDNA and FFPE samples, while we have no prior experience, we can proceed with these materials at the client’s discretion, provided they are aware of the risks and accept to bear all the associated costs.
Why is there a minimum sample requirement for Twist Exome 2.0?
- A: A minimum of 8 samples is required for Twist Exome 2.0, and customers are required to provide samples in multiples of 8 samples per batch. This requirement is due to labor costs associated with library preparation and sequencing. We do not accept fewer than the minimum number of samples unless the cline agrees to cover additional costs. Please contact the product manager for reagent availability and the number of samples per batch at least a month prior to sample collection.
What starting materials are accepted for Agilent V8?
- A: We currently accept gDNA extracted from blood, saliva, cell lines/pellets, and other tissues samples.
For FFPE samples, we have limited experience with these samples and requires an additional charge of 80 USD per sample when working with FFPE DNA. These samples can be processed at the client’s discretion, provided they are aware of the risks and accept all associated costs.
For cfDNA/ctDNA, while we have no prior experience, we are willing to proceed at the client’s discretion, with the understanding that the risks and additional costs are fully acknowledged and accepted by the client.
Why is there is a batch requirement for Agilent V8?
- A: Agilent V8 requires a minimum of 4 samples per batch for Agilent V8. This requirement is necessary to account for the labor costs associated with processing this kit. If the customer does not meet the 4-sample minimum per batch, an additional charge of 80 USD per sample will apply.
What are the differences between Agilent SureSelect V6 and Agilent SureSelect V8?
- A: Agilent SureSelect V8, released in 2022, is an updated version of SureSelect V6, which was introduced in 2016. Agilent SureSelect V8 features a more precise target size of 35.1 MB and a design size of 41.6 MB, offering improved coverage with updated genomic information.
- Can a customer compare data previously obtained with Agilent SureSelect V6 to results generated using Agilent SureSelect V8?
- A: No, data obtained using Agilent SureSelect V6 cannot be directly compared to results from Agilent SureSelect V8. This limitation arises due to significant differences between the two platforms, including variations in probe size, the versions of databases used for probe design, and the overall databases utilized. These differences result in distinct target regions and coverage, making direct comparisons unreliable.
What if my customer wants to use the discontinued Kapa HyperExome Kit?
- A: The Kapa HyperExome kit has officially been discontinued. If a customer inquiry about using this kit in alignment with an ongoing project, please contact Kejing directly to confirm if any internal stock is available. Samples must not be sent without prior confirmation from Kejing, and no samples will be accepted without this confirmation.
- Note:
If the customer is interested in using the Kapa HyperExome V2 kits, please note that no testing has been conducted with this kit, and Novogene has no prior experience using it. Projects involving this kit will need to meet special project requirements, including a sample forecast and a completed evaluation by the APM team on a case-by-case basis.
- Can we offer WES or targeted sequencing using a customer-requested kit?
- A: The feasibility of using a customer-requested kit depends on specific project requirements. The APM team will initiate the evaluation process for customized target capture sequencing only if the project includes more than 96 samples. However, due to cost considerations, this option is not recommended. For smaller projects or more cost-effective solutions, our standard WES products are highly recommended.
Information required from the customer:
Panel Details: Provide information about the panel of interest, including probe size, design size, supplier, required plex, and expected sequencing depth.
Panel Protocols: Submit detailed protocols for the panel, including a list of required reagents.
Sample and Forecast Information: Specify the number of samples, along with a sample forecast and timeline.
Customization Requirements: For customized library preparation, demultiplexing, or analysis, provide all relevant details and corresponding protocols.
Budget Information: Share the customer’s budget for the project.
Additional Requests: Communicate any specific requirements or concerns to the APM team during the evaluation process.
Risks:
If the client’s samples fail to pass QC (or proceed at risk), the client must cover the full cost of services and reagents.
If the client terminates the project midway after reagents have been purchased, the client will be responsible for the cost of all purchased reagents.
- Note:
For the sales team: Please assist in effectively managing the customer's expectations regarding the project's requirements, timelines, and associated risks.
For projects involving reagent purchases: The APM team will only proceed with procurement after the following conditions are met:
Submission of a Purchase Order (PO): The customer must provide a valid PO.
Explicit Authorization: The customer must send an email clearly authorizing the purchase of the required kits.
Due to the customized nature of this process, the APM team cannot guarantee:
The availability of specific reagents within a fixed timeframe.
The successful outcome of the project if unexpected challenges arise during sample preparation or sequencing.
This policy ensures that both the customer and internal teams are aligned, reducing potential misunderstandings and setting realistic expectations.
- Can DNBSEQ be used for WES?
- A: Currently, DNBSEQ sequencing is available only for research-based projects using Agilent SureSelect V6 panel. We are unable to provide DNBseq sequencing for any other WES panels at this time.
- Can we provide data output other than the designated 10Gb for the Human WES product with the IDT kit?
- A: For the IDT kit, if a client requires a data output other than the standard 10Gb, they must complete the "Special Requirement Evaluation Form for CAP Lab" with detailed information about their request. The number of samples and batch details are required for the lab's evaluation.
As this is a non-standard product for the CAP lab, the pricing will be higher than the standard 10Gb data output. For further details, please refer to Appendix 1 for the form.
What types of Human WES products can be performed in the CAP lab?
- A: Human WES with IDT kit: standard product offering 10Gb of raw data per sample.
Human WES with Agilent SureSelect V6: options available for 12Gb or 24Gb of raw data per sample. For pricing details, please refer to the “5 Whole Exome Sequencing” section in the price list.
What types of deliverables are offered for the corresponding kits in CAP lab?
- A: The CAP lab provides two deliverables: raw data for client analysis and a research standard analysis report, identical to the standard WES analysis. Clients can choose based on their project needs.
- Can we offer WES results with a clinical report?
- A: Unfortunately, we are unable to provide human WES results with a clinical report that includes a signature.
- Can we guarantee sequencing depth?
- A: Unfortunately, we can only guarantee the data output for samples that pass sample QC; sequencing depth cannot be guaranteed.
- What is the difference between coverage and sequencing depth?
- A: Coverage and depth are often used interchangeably in next-generation sequencing (NGS), but they represent distinct concepts essential for interpreting sequencing data.
Coverage, or breadth of coverage, refers to the percentage of the target region (e.g., genome or exome) that has been sequenced at or above a specified depth, indicating the completeness of sequencing. For example, 95% coverage means 95% of the target region is adequately sequenced. Sequencing depth, or depth, measures the average number of times each base is sequenced, reflecting the reliability of the data. A depth of 30X signifies that each base has been sequenced an average of 30 times, increasing confidence in variant detection.
Together, coverage ensures the completeness of sequencing, while depth enhances data accuracy and reliability, both of which are crucial for high-quality results in genome and exome sequencing.
- Can we provide merged VCF files?
- A: Yes, we can provide merged VCF files in the following formats:
SNP/InDel VCF files for multiple samples combined into a single VCF file.
SNP/InDel VCF files for a single sample merged into one comprehensive VCF file.
As this is a customized analysis, please include the details in the "Customized Analysis Note" section of the quotation to inform the PM team. Refer to the price list for any additional charges.
- Can we provide MAF files?
- A: Yes, we can convert annotation results into a MAF file. This service incurs an additional charge, similar to the cost of merged VCF file analysis. As this is a customized analysis, please include the details in the "Customized Analysis Note" section of the quotation to inform the PM team.
- What is the difference between SNP and SNV?
- A: ingle Nucleotide Polymorphisms (SNPs) and Single Nucleotide Variants (SNVs) are single-nucleotide changes, the most common genetic variants in the genome. SNPs are analyzed within populations, reflecting shared variations, while SNVs are identified in individual samples without population context. For consistency, our analysis reports uniformly refer to both as SNPs, in line with the demo report conventions.
- Can we provide common variation and unique variation (SNP/InDel) calling between different groups? A: Yes, we can offer common variation and unique variation among groups (SNP/InDel).
Analysis workflow:
Standard analysis for each sample.
Common variations calling (1) for Group A, common variations calling (2) for Group B, common variations calling (3) for Group C……
Comparison: same SNP/InDel between (1) and (2) are common variations between group A and B. Same with Group A and C, or Group B and C. If (1) have variation A but (2) don’t have, then it is unique variation for Group A. Same rules for Group B unique variations and other Groups.
All the results will deliver by sample level. Each sample will have common and unique variations results, including SNP/InDel calling and annotation.
- Note:
If the sample number is big, the client needs to choose the cut-off value for step 2-common variants calling for groups.
Additional price and TAT:Need evaluation case by case.
Are we able to provide somatic variant analysis for unpaired tumor samples?
- A: Yes, we can perform somatic variant analysis for unpaired tumor samples using the Panel of Normal (PON) database from GATK.
Additional Analysis cost*:
Somatic SNP/InDel only: 45 USD per sample (not including the price of Standard analysis)
Analysis Content (with PON database):
SNP/InDel calling, annotation, and statistics. Somatic SNP/InDel calling, annotation, and statistics.
Additional TAT*: 3 working days above standard product TAT
- Note:
*All the above information is for Somatic SNP/InDel analysis only, not including standard analysis. Will require standard analysis price and TAT.
- How to quote with this analysis in SFDC system?
Select the "Customized Analysis" process and include details in the "Customized Analysis Note" when preparing the quotation.
Are we able to use the PON database for samples sequenced on other platforms such as MGI-DNBSEQ T7? A: Yes, we can use the PON database for samples sequenced on other platforms, such as MGI-DNBSEQ.
This is possible because we have updated our PON database from Novogene's curated version to the GATK PON database. Please refer to FAQ
12 for pricing information.
For more PON information, please refer to the following link: https://gatk.broadinstitute.org/hc/en-us/articles/360035890631-Panel-of-Normals-PON
- Can we perform mitochondrial DNA analysis with WES data? If so, what is the recommended sequencing depth and cost?
- A: Yes, mitochondrial DNA (mtDNA) analysis can be performed using Human WES data. However, with approximately 100X WES sequencing, the expected mean coverage depth for mtDNA is only around 10X.
For better results, we recommend using 5X human WGS (15Gb), which provides a mean mtDNA coverage depth of approximately 400-600X based on our testing data. For clients requiring even higher coverage, 30X human WGS is preferred, offering an expected mean mtDNA coverage depth of approximately 5000X.
Additional Analysis Cost*:
SNP/InDel: 25-30 USD per sample
Analysis content (Only mitochondrial DNA analysis) *:
Data quality control: filtering reads containing adapter or with low quality. Alignment to reference genome; statistics of sequencing depth and coverage. SNP/InDel calling, annotation and statistics.
Additional TAT*: 4-5 working days per 50 samples above standard product TAT.
Delivery content*:
Raw data (fastq);
Analysis result: bam, vcf, annotation if data analysis is required Project report for SNP/InDel analysis.
- Note:
* The above information applies solely to mitochondrial DNA analysis and does not include standard analysis, which is not required for this service.
- How to quote with this analysis in SFDC system?
Select the "Customized Analysis" process and include details in the "Customized Analysis Note" when preparing the quotation.
Are we able to provide variant allele frequency (VAF) results for WES analysis? A: Yes, we can provide VAF results for SNP and InDel as part of the data release.
Sample required:
Tumor/ Normal paired samples, as it is based on somatic standard analysis.
Additional Analysis Cost*:
SNP/InDel: 40-45 USD/ case, (for up to 20 samples)
Analysis Content (only VAF):
VAF SNP/InDel calling, annotation and statistics.
Additional TAT*: 2 working days per 50 samples above standard product TAT.
Delivery content*:
Analysis result: bam, vcf, annotation if requires data analysis;
- Note:
*All the above information is for VAF analysis only, not including standard analysis. Somatic standard analysis is a required analysis.
- How to quote with this analysis in SFDC system?
Select the "Customized Analysis" process and include details in the "Customized Analysis Note" when preparing the quotation.
- What is the purpose of the VAF analysis?
- A: Variant Allele Frequency (VAF) serves as a surrogate measure to quantify the proportion of DNA molecules in the original specimen that carry a specific genetic variant. VAF is a valuable tool in advanced cancer research, enabling insights into tumor purity, ploidy estimation, and intra-tumor heterogeneity, which are critical for understanding tumor biology and progression.
- Can we provide loss of heterozygosity (LOH) analysis?
- A: Yes, we offer LOH analysis. However, we recommend that customers consider whole-genome sequencing (WGS) for this analysis, as LOH results are dependent on CNV (Copy Number Variation) data, which are more reliably obtained from WGS. Loss of heterozygosity (LOH) involves the loss of one parental allele at a specific locus, often linked to tumor suppressor gene disruption in cancer. Combining LOH with CNV data offers insights into genomic instability, aiding in identifying driver mutations and therapeutic targets. Whole-genome sequencing is the preferred method due to its broader coverage and higher resolution.
Sample required:
Tumor/ Normal paired samples, as it is based on somatic standard analysis.
Additional Analysis Cost*:
15-20 USD per sample
Analysis Content (LOH):
LOH results
Additional TAT*: 2 working days per 24 samples above standard product TAT.
Delivery content*:
Excel document.
- Note:
*All the above information is for LOH analysis only, not including standard analysis. Somatic standard analysis is a required analysis.
- How to quote with this analysis in SFDC system?
Select the "Customized Analysis" process and include details in the "Customized Analysis Note" when preparing the quotation.
- Can we provide HLA typing for MHC class II for our HLA typing analysis?
- A: Our standard HLA typing, as described in the product manual, is performed using PolySolver software, which provides HLA typing for MHC Class
I only. If the customer requires HLA typing for both MHC Class I and II, we can offer this analysis using HLA-HD software. The cost for HLA-HD typing analysis is $45 USD per sample.
Since this is a customized analysis, please include a remark in the quotation to inform the Project Manager (PM).
Do we offer customized analysis for using WES results to study specific disease-related genes?
- A: Yes, we offer DisGeNET analysis, which provides gene-disease association analysis for relevant genes and variants linked to a specific disease selected by the customer from an available list. To access the list of diseases, please contact the APM team.
Please note that the results generated are for research purposes only and are not intended for clinical use.
Sample required:
Disease or Trio samples
Additional Analysis Cost*:
100 USD per project (for up to 20 samples)
Analysis Content:
DisGenNet Annotation results and Phenolyzer Analysis Results
Additional TAT*: 2 working days per 24 samples above standard product TAT.
Delivery content*:
Excel document
- Note:
*All the above information is for this customized analysis only, not including standard analysis. Standard analysis is a required analysis.
- How to quote with this analysis in SFDC system?
Select the "Customized Analysis" process and include details in the "Customized Analysis Note" when preparing the quotation.
- Can we offer Neoantigen prediction analysis?
- A: Yes, we provide WES and RNA-Seq data for Neoantigen detection conjoint analysis. The requirements are as follows:
Sample requirement:
WES data: Tumor and normal paired samples.
RNA-Seq data: Tumor samples are required for joint analysis.
Required data amounts:
WES: 24Gb for tumor samples and 12Gb for normal samples.
RNA-Seq: 12Gb for tumor tissue. (For FFPE RNA, only the TruSeq Access workflow is available.)
Analysis price:
Refer to the price list for WES and FFPE RNA-Seq standard analysis.
Additional cost for Neoantigen prediction: $330–350 USD per set of samples (WES + RNA) based on the above data amounts.
For data amounts exceeding these recommendations, please consult the APM team for pricing.
Turnaround Time (TAT):
Combined analysis (WES standard + RNA-Seq standard + Neoantigen prediction): 10–12 working days for up to 20 sample sets.
Analysis Workflow:
Data Release Format:Results will be provided in Excel format.For additional information or specific requirements, please contact the APM team.Data Release Format:Results will be provided in Excel format.For additional information or specific requirements, please contact the APM team.Detailed workflow available upon request.
Data Release Format:
Results will be provided in Excel format.
For additional information or specific requirements, please contact the APM team.
Data Release Format:
Results will be provided in Excel format.
For additional information or specific requirements, please contact the APM team.
Mouse Whole Exome Sequencing
## Sample Requirements
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/Agarose Gel)
Strongly Recommended
Required
Mouse Exome Library
Genomic DNA
≥ 600 ng
≥ 300 ng
≥ 20 μL
≥ 15 ng/μL
OD260/280 = 1.8 – 2.0,
no degradation, no contamination
FFPE
≥ 1.0 μg
≥ 400 ng
≥ 20 μL
≥ 15 ng/μL
Fragments should be longer than 1000 bp
Sequencing Strategy and Turnaround Time
Library Type
Library Preparation Kit
Sequencing
Strategy
Recommended Sequencing
Depth
Turnaround Time* (≤ 24 samples)
WOBI
WBI
Mouse Exome Library
Agilent SureSelectXT Mouse All Exon Kit (49.6M)
NovaSeq PE150
For Mendelian disorder/complex disease: ≥ 50×
For tumor sample: ≥ 100×
30 working days
35 working days
Analysis Contents
Standard Analysis
Software
Data quality control: filtering reads containing adapters or with low quality
fastp
Alignment with reference, statistics of sequencing depth, and coverage
BWA, Sambamba
Germline SNP and InDel calling, annotation, and statistics
GATK, ANNOVAR
Somatic variant detection (only apply for tumor-normal paired samples)
-SNP calling, annotation, and statistics
-InDel calling, annotation, and statistics
-CNV calling, annotation, and statistics
SNP: MuTect InDel: Strelka CNV: Control-freec
Annotation: ANNOVAR
Demo for data release structure: WOBI:
03. Variant and AnnotationWBI：Standard analysis- Unpaired samples:03. Variant and AnnotationWBI：Standard analysis- Unpaired samples:
03. Variant and Annotation
WBI：
Standard analysis- Unpaired samples:
03. Variant and Annotation
WBI：
Standard analysis- Unpaired samples:
Standard analysis- Paired samples:
03. Variant and Annotation03. Variant and Annotation
03. Variant and Annotation
## FAQ
What needs to be confirmed about the Mouse WES kit before providing a quotation?
- A: Before quoting for the Mouse Exome Hybridization kit, please confirm with the customer the number of samples and the sample submission plan. Then, please contact the APM team to verify reagent availability.
Why is there is a batch requirement for Mouse WES kit?
- A: Mouse WES kit requires a minimum of 4 samples per batch. This requirement is necessary to account for the labor costs associated with processing this kit. If the customer does not meet the 4-sample minimum per batch, an additional charge of 80 USD per sample will apply.
What does FFPE stand for, and what is the additional charge for library preparation? A: FFPE stands for Formalin-Fixed, Paraffin-Embedded.
An additional charge of 80 USD per sample applies for library preparation when working with FFPE DNA or FFPE samples.
What special considerations are required for TAT?
- A: The TAT listed in the form applies only to projects using reagents currently in stock. As reagent availability fluctuates daily, additional time may be required for restocking if sufficient quantities are not available. The estimated delivery time for restocked reagents is approximately 2–3 months. Please confirm reagent availability with the APM team before proceeding.
- Can the Mouse WES kit be used for other organisms, such as rats?
- A: No, the Mouse WES kit is specifically designed for mice and cannot be used for WES sequencing of other organisms.
Appendix 1 Special Requirement Evaluation Form for CAP labAppendix 1 Special Requirement Evaluation Form for CAP lab
Appendix 1 Special Requirement Evaluation Form for CAP lab
（一）The Application for Special Requirement
Department
AMEA
Applicant
Date of Application
Purpose
Special requirement details
Expected result
Expected Completion date
Remarks
（二）评估结果(Lab evaluation results)
评估结果反馈
评估人
评估日期
承诺完成时间
（三）签字确认
需求部门负责人
日期
评估部门负责人
日期
Novogene Product Manual
Metagenomic and Meta-transcriptomic Sequencing
AMEA 2025.06
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director. If you have any questions about the products, please consult the APM team.)
Product Manual Revisions
Subject
Novogene Product Manual-6 Metagenomic Product Manual-2025 V2.0
Revision Number
2025 V2.0
Issue Date
June 27th, 2025
Prepared by
Chen Yu
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2024 V1.0
Pg 4-Battle Card Update
Pg 7-Analysis Content Comparison Update Pg 8-DNA extraction Update
Pg 9-Sample Requirement Update
Pg 9: Sequencing Strategy and Turnaround Time
Pg 11-Analysis Content Update (MetaPhlAn-HUMAnN) Pg 14-WBI demo data release for MetaPhlAn4-HUMAnN3 Pg 14-FAQ 1: Example Questions
Pg 17-FAQ 2: Removal of shallow shotgun metagenomic sequencing Pg 17-FAQ 3: Difference between reads-mapping and assembly-based.
Pg 18-FAQ 4: Difference in sample requirement, library prep and sequencing. Pg 18-FAQ 5: Projects suited for reads-mapping.
Pg 20-FAQ 11: Host contamination susceptibility with low sequencing depth. Pg 21-FAQ 14: Positioning between MetaPhlAn4-HUMAnN3 vs Assembly Pg 21-FAQ 15: Sample type for MetaPhlAn4-HUMAnN3
Pg 21-FAQ 16: Differences in our analysis pipeline Pg 23-FAQ 19: MGE annotation results
ChenYu
Sept 25th, 2024
2024 V2.0
Pg 5-Battle Card Update
Pg 8-Analysis Content Comparison Update Pg 14-Analysis Content Update (Kraken2) Pg 18-WBI demo data release for Kraken2 Pg 18-FAQ 1: Example Questions
Pg 24-FAQ 14: Positioning between MetaPhlAn4-HUMAnN3 vs Assembly Pg 26-FAQ 16: Differences in our analysis pipeline
Pg 27-FAQ 17: Kraken2 and virus/protist annotation
ChenYu
Nov 30th, 2024
2025 V1.0
Pg 31-added long-reads shotgun metagenomic sequencing with PacBio Pg 32-(PacBio Meta) FAQ 3: Analysis in development
Pg 32-(PacBio Meta) FAQ 4: Not MAG analysis
Pg 33-added long-reads shotgun metagenomic sequencing with ONT Pg 35-(ONT Meta) FAQ 3: NGS requirement for analysis
Chen Yu
May 31st, 2025
2025 V2.0
Pg 11-added Metatranscriptome Sequencing
Pg 12-(Meta-trans) Updated sample requirements Pg 12-(Meta-trans) Added data release structure
Pg 14-(Meta-trans) FAQ 3: sample requirement for DNA and RNA extraction Pg 40-(ONT Meta) FAQ4: Data release format
Chen Yu
June 27th, 2025
Contents
Microbial Solutions: Metagenomic Samples Battle Card6
Comparison Chart6
Analysis Content Comparison9
Meta-transcriptome Sequencing11
RNA Extraction (SG Outsource)11
## Sample Requirements12
Sequencing Strategy and Turnaround Time12
Analysis Contents12
Demo for data release structure13
## FAQ14
Shotgun Metagenomics Sequencing (NGS)16
DNA extraction16
Sample Requirement17
Sequencing Strategy and Turnaround Time17
Analysis Contents18
Demo for data release structure*21
## FAQ24
Long Reads Shotgun Metagenomics (PacBio)36
## Sample Requirements36
Sequencing Strategy and Turnaround Time36
4. FAQ37
Long Read Shotgun Metagenomic Sequencing (Nanopore)38
## Sample Requirements38
Sequencing Strategy and Turnaround Time38
Analysis Contents39
## FAQ39
Microbial Solutions: Metagenomic Samples Battle Card
Comparison Chart
Product Types
Deep Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Shotgun Metagenomics Reads-Mapping (Kraken2)
Amplicon Sequencing
16S Full-length Amplicon Sequencing
PCR Product
/Customized Amplicon Sequencing
## Sample Requirements
DNA amount
≥100ng, DNA volume ≥
20 µl.
DNA amount
≥100ng DNA volume ≥
20 µl.
DNA amount
≥100ng DNA volume ≥
20 µl.
DNA amount ≥
200ng,
DNA volume ≥
20 µl.
DNA amount ≥ 300ng, Concentration ≥ 10ng/ µl
DNA amount
≥1.5µg DNA volume ≥
20 µl
Sample Types
Human Environmental, Bacteria Animal and
Plants
Human, Animal*
Human, Animal Environmental
Human Environmental, Bacteria, Animal and
Plants
Human Environmental, Bacteria, Animal and
Plants
Human-based, Environmental, Bacteria Animal and
Plants
Data Requirement
6-12Gb+
3-12 Gb+
100K raw tags
20-40K clean reads
1M raw reads (no barcodes) or 100k raw tags (with barcodes)
Sequencing Platform
Illumina NovaSeq PE150
Illumina NovaSeq 500 Cycles
PacBio Revio
Illumina NovaSeq 500 Cycles**
Taxonomic Resolution
Species/Sub-species level
Species-Level
Genus Level (Limited Species-Level)
Species/Sub-Species Level
Genus Level (Limited Species-Level)
Taxonomic Coverage
All Taxa
All taxa
Amplification region Specific
Bacteria and Archaea (16S only)
Amplification region Specific
Genome Reconstruction
Yes
No
Databases
K-mers (Scaftigs)
Marker Genes
K-mer (LCA)
Marker Genes
Ribosomal Genes
Marker Genes
Taxonomy Annotation
Micro_NR / NR database
MetaPhlAN4/ HUMANn3
Kraken2 (PlusPFP if requested)
Qiime1/ Qiime2
Qiime2
Qiime1/ Qiime2
Function Annotation
KEGG, EggNOG, CAZy, PHI, VFDB
MetaCyc, KEGG, GO, EggNOG,
Pfam
KEGG, GO,
EggNOG, Pfam
No
Antibiotic Resistance Annotation
CARD, Integrall, isfinder, Plasmid
No
Amplicon contamination
No
Yes
Host DNA Contamination
High (sample type-dependent, requires host removal)
High (sample type-dependent, requires host removal) *
Low
- Note:
* Reads-Mapping based shotgun metagenomic sequencing is very susceptible to host contamination and we will need the customer to provide us with samples with less than 50% of host contamination within the total raw reads. At the moment, our MetaPhlAn4-HUMAnN3pipeline is better suited for gut and fecal related samples, while our Kraken2 is better suited for environmental samples.
** For PCR Products and customized amplicons, the majority of samples are still being sequenced on Illumina NovaSeq 500 Cycles (PE256). However, there are exceptions and we do accept samples for PE150 as well. Please submit an inquiry to the APM team for more clarification if needed.
2. Analysis Content Comparison
Product Types
Deep Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Shotgun Metagenomics Reads-Mapping (Kraken2)
Amplicon Sequencing
Analysis Similarity
Taxonomic Annotation
Alpha Diversity
Beta Diversity analysis
Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Taxonomic Annotation
Alpha Diversity
Beta Diversity analysis
Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Taxonomic Annotation
Alpha Diversity
Beta Diversity analysis
Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Taxonomic Annotations
Alpha Diversity
Beta Diversity analysis
Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Analysis Difference
Metagenome Assembly
Gene Prediction
Function Annotation
Antibiotic Resistance Gene Annotation
- Function Annotation
Function Prediction*
Environmental Association Analyses**
Network Analysis**
Key Points
Predicted Genes
Species-Function Correlation
Metabolic Pathway
Antimicrobial Analysis
Bacteria, Archaea, Fungi, Viruses, Protists,etc
Fast TAT
Microbiome studies
Better accuracy than Kraken2
Clinical/Treatment group
Bacteria, Archaea,
Fast TAT
Environmental/Complex samples
More false positives than MetaPhlAn4-HUMAnN3
Suitable for virus and protists annotation.
Bacteria, Archaea, Fungi, Viruses,
Protists,etc
Fast TAT
Specific to one microbial taxonomy of interest (16S=Bacteria/Archaea).
Customized primer and databases
- Note:
* One round of function prediction is part of the standard analysis for Qiime2 but it is also considered a part of our advance analysis for both Qiime1 and Qiime2
** Environmental association analyses and network analysis are part of the advance analyses for both Qiime1 and Qiime2 in Amplicon Sequencing.
Meta-transcriptome Sequencing
Meta-transcriptomics refers to the study of all RNA transcripts within a microbial community (e.g., soil, water, or gut samples) at a specific timepoint, capturing the dynamic gene expression profiles that fluctuate with environmental conditions. Through next-generation sequencing (NGS), this approach provides comprehensive insights into active microbial processes by enabling community-wide expression profiling, taxonomic identification of both prokaryotic and eukaryotic members, analysis of differentially expressed genes, and functional pathway characterization. Meta-transcriptome sequencing thus serves as a powerful tool for investigating real-time microbial activity, ecological interactions, and adaptive responses within complex natural systems.
RNA Extraction (SG Outsource)
Sample types
Recommend Input
Transportation
Soil
Collect soil sample in soil preservation solution, e.g. Qiagen LifeGuard Soil
Preservation solution.
Weigh 2 g of soil/sludge sample in 15 ml screw cap tube
Add 5 ml of soil/sludge preservation solution
Vortex or invert tube by hand until the entire soil/sludge sample and preservation solution are mixed well. Excess preservation solution should be sitting on top of the soil sample.
Store sample in 4°C for overnight, transfer to -20°C freezer on the next day.
No. of replicates: 2
Dry Ice
- Note: We require pre-submission evaluation of your samples; please provide the sample quantity, photographs, and preservation method details for technical assessment. This ensures we can properly process your samples for RNA extraction.
## Sample Requirements
Sample Type
Remarks
Amount
RIN
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
Total RNA sample
Strongly Recommended
≥ 1 μg
≥ 5.8
≥ 20 μL
≥ 25 ng/μL
OD260/280 > 2.0
No degradation, no contamination
Required
≥ 400 ng
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
Meta-transcriptome library
NovaSeq PE150
12 Gb
18-20 working days
35 working days
Analysis Contents
Standard Analysis
Software
Data Quality Control: filtering reads containing adapter or with low quality
fastp
Statistics Analysis of Data Production and Quality
-
Remove host sequence (Analyze when selecting host)
Bowtie2
De novo Assembly
Trinity+Corset
Gene Functional Annotation (GO,eggNOG, KEGG, CAZy annotation)
Diamond/hmmscan
Taxonomic Analysis
Diamond/MetaStats
Gene Expression Analysis
RSEM
Differential Expression Analysis (two or more groups of samples)
DEGSeq/DESeq /edgeR
GO Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
GOSeq,topGO,hmmscan
KEGG Pathway Enrichment Analysis of Differentially Expressed Genes (DEGs) (two or more groups of samples)
KOBAS
Comparative Analysis between Various Samples (3 or more samples, including eggNOG/COG functional comparisons, cluster analysis and PCoA analysis)
-
Protein Protein Interaction Analysis of differentially expressed coding genes
BLAST
Demo for data release structure
WOBI
WBI
## FAQ
- What is the library type and library size of meta-transcriptome library?
- A: We prepare non-directional libraries with 250-300bp insert sizes, including rRNA depletion as standard.
Directional libraries are available upon request (please see price list) with advance notification to the Project Coordinators.
- How is rRNA depletion performed for meta-transcriptome samples?
- A: Our standard protocol removes both eukaryotic and prokaryotic rRNA. The specific approach depends on the sample origin:
For defined animal/plant samples: Prokaryotic + host (animal or plant) rRNA removal For undefined samples: Comprehensive removal of prokaryotic, animal, and plant rRNA This ensures optimal mRNA enrichment regardless of sample composition.
- Can the same sample (soil/fecal) be used for both DNA and RNA extraction for metagenomic and metatranscriptomic sequencing? A: Yes, but the customer must:
Provide sufficient sample quantity to meet both DNA and RNA extraction requirements
Submit the material in two separate tubes (one designated for DNA, one for RNA)
This is necessary because DNA and RNA extractions are performed separately using distinct protocols. Providing pre-separated samples ensures optimal results for both sequencing applications.
What are the differences between meta-transcriptome and dual RNA seq?
- A:
Meta-transcriptome
Dual RNA-seq
Sample type
Multiple species from environment
Two species
(host and pathogen)
Reference genome
Without reference genome
With reference genome
Analysis method
Assemble
Alignment
Analysis content
Taxonomic analysis of complex microbial communities
Host-pathogen interaction initiates gene expression changes
Shotgun Metagenomics Sequencing (NGS)
Metagenomics takes the entire microbial community in a specific habitat as the research object, and directly extracts the DNA of environmental samples for sequencing without separation and culture. It studies the community structure, species classification, systematic evolution, gene function, and metabolic network of environmental microorganisms, and has been widely used in microorganisms.
DNA extraction
Sample types*
Species
Recommended Input
Replicates
Tube Recommendations
Transportation
Stool
Human/Animal
≥ 2ml
2
DNA shield reagent or Invitek Stool collection tube
Follow tube specification
Stool (Qiagen)
(96 samples at a time required) **
Human
˃ 250mg
3
1.5ml Eppendorf tube
Dry Ice
Saliva
Human
≥ 4ml
2
Oragene DNA
(DNA Genotek) Collection tube
Dry Ice
Buccal Swabs/ Tongue Swab/ Mouth/ Cheek
Human
≥ 4
Don’t put lysis buffer
2
Sterile, pre-cooled 1.5/2.0ml EP tube
Dry Ice
Soil/ Sludge***
NA
Transfer to a microcentrifuge tube
3
1.5ml Eppendorf tube
Room temperature
- Note:
Please check with the APM team on kit availability for any projects that will need DNA extraction in SG lab for over 50 samples/batch. For more details, please refer to the Sample Extraction Services in the price list.
** Stool DNA extraction using the Qiagen Kit requires 96 samples at a time so we recommend customers to send samples in multiples of 96 samples. We do not accept samples that are less than 96 samples at a time. Please also reach out to the APM ahead of time with the information of when customers plan to send in their samples and their sample number.
*** For sludge samples or any sediment samples that are high in water content, please have the customer spin down their samples and provide only the spun down solids to us for DNA extraction. For more details, please reach out to the APM team for an evaluation.
Sample Requirement
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/Agarose gel)
Metagenomics library*
Total DNA
≥ 100 ng
≥ 20 μL
≥ 5 ng/μL
OD260/280 = 1.8-2.0,
No degradation, no contamination, no color
- Note:
Please note that sample requirements are the same for our shotgun metagenomics sequencing whether the customer plans to do assembly-based or reads-mapping based analysis.
Sequencing Strategy and Turnaround Time
Product
Platform Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 20 samples)
Simple Environment
Complex Environment
WOBI
WBI
Shotgun metagenomics (Assembly-based)
NovaSeq PE150
6 Gb raw data
12 Gb raw data
15 working days
30 working days
Shotgun metagenomics (Reads-Mapping)
NovaSeq PE150*
3 Gb raw data**
12 Gb raw data
15 working days
30 working days
- Note:
Please note that sequencing strategy is the same for our shotgun metagenomics sequencing whether the customer plans to do assembly-based or reads-mapping based analysis.
** We still recommend the customer to consider deeper sequencing depth (6Gb of raw data) for reads-mapping based approach, if possible, especially since a shallower sequencing depth is more susceptible to host-contamination factors.
Analysis Contents
Standard Analysis (Deep Shotgun Metagenomics)
Software
Data quality control: filtering reads containing adapters or low-quality reads, filtering host genome sequences
fastp, bowtie2, Samtools
Assembly
MEGAHIT
Gene Prediction and Abundance Analysis:
Gene catalogue statistics, Core-pan genome analysis, Gene number analysis, Correlation analysis of samples, Venn analysis, flower analysis, and gene box
MetaGeneMark, CD-HIT， Bowtie2, samtools, R
Taxonomy Annotation:
Species annotation (MicroNR*), Krona, Abundance heatmap, PCA, NMDS, PCoA, Cluster Tree, Abundance top10, Anosim, MetaGenomeSeq(Requires 3 samples in 1 group Only 2 groups) and LEfSe(Requires 3 samples in 1 group At least 2 groups), Random Forest (Requires 15 samples in 1 group Only 2 groups)
DIAMOND, LCA algorithm, R, LEfSe, MetaGenomeSeq
Function Annotation:
Gene annotation (KEGG (pathway maps), eggNOG, CAZy, VFDB, PHI databases), Functional abundance bar graphs, Functional distribution heatmap, PCA, NMDS, PCoA, Anosim, MetaGenomeSeq(Requires 3 samples in 1 group Only 2 groups) and LEfSe(Requires 3 samples in 1 group At least 2 groups), Random Forest (Requires 15 samples in 1 group, only 2 groups)
DIAMOND, R, LEfSe, MetaGenomeSeq
Antibiotic Resistance Gene Annotation
Gene annotation (CARD, MGEs database), Bar plot, box plot, heatmap, PCA, PCoA, NMDS, and Circos, MetaGenomeSeq(Requires 3 samples in 1 group Only 2 groups), LEfSe(Requires 3 samples in 1 group， at least 2 groups), Venn analysis, flower analysis, Anosim
Resistance Gene Identifier (RGI), R, Circos, LEfSe, MetaGenomeSeq, tblastn
- Note:
Please refer to FAQ 13 for more information on which database to recommend to the customer.
Standard Analysis (MetaPhlAn-HUMAnN)
Software
Data quality control: filtering reads containing adapters or low-quality reads, filtering host genome sequences*
fastp, bowtie2, Samtools
Taxonomy Annotation:
Species annotation (MetaPhlAn), Abundance top10, Abundance heatmap, Alpha Diversity Indices, Cluster Tree, PCA, PCoA, NMDS, Anosim, MetaGenomeSeq(Requires 3 samples in 1 group Only 2 groups) and LEfSe(Requires 3 samples in 1 group At least 2 groups)
MetaPhlAn, R perl, LEfSe, MetaGenomeSeq
Function Annotation and Statistical Analysis:
Gene annotation (MetaCyc, KEGG (KO, EC, Pathway, Module), GO, eggNOG, Pfam databases), Abundance top 10, Functional distribution heatmap, Alpha Diversity Indices, Cluster Tree, PCA, PCoA, NMDS, Anosim, MetaGenomeSeq (Requires 3 samples in 1 group Only 2 groups) and LEfSe(Requires 3 samples in 1 group At least 2 groups)
HUMAnN, R, perl, Qiime, LEfSe, MetaGenomeSeq
- Note:
We cannot accept samples with high host DNA contamination. When host DNA is present, we typically need to remove the corresponding
reads from the sequenced data. If the contamination level is high, a significant portion of the reads may be removed, which could result in insufficient data for further analysis.
Standard Analysis (Kraken2)
Software
Data quality control: filtering reads containing adapters or low-quality reads, filtering host genome sequences*
fastp, bowtie2
Taxonomy Annotation:
Species annotation (Kraken2), Abundance top10, Abundance heatmap, Alpha Diversity Indices, Cluster Tree, PCA, PCoA, NMDS, Anosim, MetaGenomeSeq(Requires 3 samples in 1 group Only 2 groups) and LEfSe(Requires 3 samples in 1 group At least 2 groups)
Kraken2/Braken, PlusPFP** if requested, R perl,R, LEfSe, MetaGenomeSeq
Function Annotation and Statistical Analysis:
Gene annotation (KEGG (KO, EC, Pathway, Module), GO, eggNOG, Pfam databases), Abundance top 10, Functional distribution heatmap, Alpha Diversity Indices, Cluster Tree, PCA, PCoA, NMDS, Anosim, MetaGenomeSeq (Requires 3 samples in 1 group Only 2 groups) and LEfSe(Requires 3 samples in 1 group At least 2 groups)
Diamnond, R, perl, R, LEfSe, MetaGenomeSeq
- Note:
We cannot accept samples with high host DNA contamination. When host DNA is present, we typically need to remove the corresponding reads from the sequenced data. If the contamination level is high, a significant portion of the reads may be removed, which could result in insufficient data for further analysis.
** If customer is interested in viral, protists and some plants annotation, please request for PlusPFP database.
Demo for data release structure*
WOBI**
- Note:
Please note that the WOBI structure will be same for assembly-based and reads-mapping based analysis.
** Clean data will be provided only upon customer request, and the customer will need to pay for the release of clean data according to the price list.
WBI for Assembly-Based Analysis:
- Note:
Please refer to the price list for standard analysis price when quoting for assembly-based analysis shotgun metagenomic sequencing.
** Clean data will be provided only upon customer request, and the customer will need to pay for the release of clean data according to the price list.
WBI for Reads-Mapping Analysis (MetaPhlAn4-HUMAnN3)
- Note:
Please refer to the price list for Reads-mapping (MetaPhlAn) analysis when quoting for reads-mapping based MetaPhlAn4-HUMAnN3 analysis shotgun metagenomic sequencing.
** Clean data will be provided only upon customer request, and the customer will need to pay for the release of clean data according to the price list.
WBI for Reads-Mapping Analysis (Kraken2)
- Note:
Please refer to the SFDC for Reads-mapping (Kraken2) analysis when quoting for reads-mapping based Kraken2 analysis shotgun metagenomic sequencing.
** Clean data will be provided only upon customer request, and the customer will need to pay for the release of clean data according to the price list.
*** If customer is interested in the previous Kraken2 analysis, please notify the project manager ahead of time.
## FAQ
What questions should you ask when a customer is interested in shotgun metagenomic sequencing?
- A: Please refer to the table below for example questions for new shotgun metagenomic sequencing inquiries.
Question Types
Questions to Ask the Customer
Follow-up Clarification Questions
Possible Solutions
A1.1 If the customer would like species level,
then shotgun metagenomics is a suitable option
Q1. What is the primary research
goal?
Q1.1 Taxonomy identification to species level? Yes, to A1.1; No, to A1.2.
for this customer.
A1.2 If the customer does not need species-level, we still recommend the customer to
consider shotgun metagenomic sequencing if
they have the funding.
A2.1 If the customer is only interested in
species-level annotation and some taxonomy
annotation, then the customer may consider
Q2. Are there any
Q2.1 Do they wish to obtain possible gene
reads-mapping based shotgun metagenomic
additional research
information or metabolic pathway information or
sequencing depending on their sample
Research-
goals that the
antibiotic resistance gene information? No, to
situation. Please refer to Q3.
based
customer is
A2.1; Yes, to A2.2.
A2.2. If the customer is interested in any
Questions
interested in?
Q2.2 Do they wish to see the correspondence
information regarding gene information,
Yes, to Q2.1; No, to
between species and function information? No,
metabolic pathway, antimicrobial resistances
Q3.
to A2.1; Yes, to A2.2.
gene and correspondence between species
and function, then the customer can only select
assembly-based shotgun metagenomics
sequencing.
Q3. Is the customer
Q3.1 Is the customer interested in studying viruses or protists?
Yes, to A3.1; No, to Q3.2.
Q3.2, Is the customer interested in studying in non-microbial species like helminths alongside their microbial species?
Yes, to A3.2; No, to Q4.
A3.1 If the customer is interested in viruses or protists, then the customer can only select assembly-based shotgun metagenomic sequencing with the NR database. Please refer to FAQ 13.
A3.2. Please submit an inquiry to the APM
team if the customer is interested in studying
interested in specific
types of
microorganisms?
Yes, to Q3.1; No, to
Q4.
non-microbial organisms like helminths alongside their microbial species.
Q4.1 Is the customer working with animal-
A4.1 If the customer is working environmental-
Q4. What kind of
human based samples?
based samples, please refer to FAQ 9 for the
sample is the
Yes, to Q5；No, to A4.1.
recommended sequencing depth.
customer working
Q4.2. Is the customer working with
A4.2 Please submit an inquiry to the APM team
with?
environmental-based samples?
if the customer is working with a unique sample
Yes, to A4.1; No, to A4.2.
type.
A5.1 If the customer’s samples have high host
contamination, amplicon sequencing is
generally recommended instead of shotgun
Q5. Does the
metagenomic sequencing. If the customer is
Sample-based Questions
customer’s samples have host contamination?
Yes, to Q5.1, No, to
Q5.1 Is the customer working with samples of high-host contamination?
Yes, to A5.1; No, to A5.2.
insistent on proceeding with shotgun metagenomic sequencing, a higher sequencing depth is recommended (at least ≥ 12Gb).
A5.2 If the customer’s samples have some host
Q6.
contamination but the host contamination is
relatively low, assembly-based shotgun
metagenomic sequencing is recommended.
Please refer to FAQ 10 for more information.
Q6. Does the customer require any DNA extraction services?
Yes, to Q6.1; No, to Q7.
Q6.1. Has the customer done any pretreatment to their samples?
Yes, to A6.2, No, to A6.1.
A6.1. Please refer to our DNA extraction service list for more information or submit an inquiry to the APM team for an evaluation.
A6.2. Samples that had gone through any pretreatment will require an inquiry to the APM team for an evaluation. Please clarify with the
customer on the type of pretreatment done to
their samples and the samples current state
prior to submitting the inquiry.
A7.1. Host-contamination removal is typically
Q7. Does the customer need host-DNA contamination removal?
Yes, to Q7.1; No, to Q8.
Q7.1 Does the customer have the reference genome for the host DNA?
Yes, to A7.1; No, to A7.2.
provided alongside analysis. If the customer wish for us to provide host-contamination removal when the project is WOBI, please submit an inquiry for this project as there will be an additional cost and TAT for this service for the WOBI option.
A7.2 Please submit an inquiry to the APM team
for an evaluation.
Analysis-based Questions
A8.1. If the customer is interested in viruses or protists alongside gene information or species-function relationship, then the customer can
only select assembly-based shotgun
Q8. Is the customer interested in receiving annotation results related to
viruses and protists?
Q8.1 Does the customer require gene information or any species-function relationship information?
Yes, to A8.1; No, to A8.2.
metagenomic sequencing with the NR database. Please refer to FAQ 13 for more information on the difference between these 2 databases.
A8.2 If the customer does not any preference,
another option for consideration will be Kraken2
since reads-mapping can provide easier
annotation for viruses and more complex
microbes like protists.
Why have we removed shallow shotgun metagenomic sequencing from our price list?
- A: Although we have removed shallow shotgun metagenomic sequencing from our price list, the technique itself is still available. Shallow
shotgun metagenomics refers to sequencing a smaller volume of data, typically 1-3 Gb, compared to the ≥6-12 Gb required for deep shotgun metagenomics. This lower sequencing depth can impact downstream analyses, which is why we offer reads-mapping analysis as an optional analysis service for shotgun metagenomic sequencing.
- What is the main difference between the data used for reads-mapping analysis and assembly-based analysis?
- A: Reads-mapping analysis is typically offered for sequencing depths lower than 6 Gb, as it relies on the sequenced reads for both taxonomy annotation, function annotation and subsequent analysis. In contrast, assembly-based analysis requires more data, so a sequencing depth of less than 6 Gb per sample is insufficient for this method. The difference in sequencing depth significantly affects the type of analysis results customers will receive, with reads-mapping being more suitable for lower-depth data and assembly-based analysis requiring higher sequencing depth.
Is there any difference between the sample requirement, library preparation and sequencing for assembly-based and reads-mapping based shotgun metagenomics?
- A: No, there is no difference in the sample requirements, library preparation, or sequencing platforms between these two approaches. The only distinction lies in the sequencing depth, which determines the type of analysis that is most suitable—reads-mapping for lower depths and assembly-based for higher depths.
What kind of projects are suited for reads-mapping shotgun metagenomic sequencing with a lower sequencing depth?
- A: Reads-mapping shotgun metagenomics is a good alternative to amplicon-based methods, especially when you need species-level resolution or want to amplify multiple target regions from the same sample. It provides better taxonomy annotation than amplicon sequencing, making it ideal for projects that use amplicon results as a reference for deeper shotgun metagenomics. It’s also a helpful
option for projects with multiple target regions, where meeting sample requirements or choosing the right primers might be challenging with amplicon-based methods.
- How to ship tissue samples from overseas?
- A: If the tissue sample type is on our extraction list, the client can ship the samples directly. All tissue samples should be flash-frozen in liquid nitrogen and shipped with dry ice. For information about shipping and potential costs, please contact the logistics team.
If the tissue sample type is not on the extraction list, please reach out to the Product Manager for extraction capabilities and the logistics team for shipment and cost details regarding tissue sample extraction.
- What is the lowest sample amount that we can accept?
- A: Based on Novogene’s experience, the minimum amount of total DNA we can accept is ≥80 ng per sample. However, please note that
this is considered a risky amount for library preparation and sequencing, and the data output per sample is not guaranteed.
What characterizes a sample from a "simple environment”?
- A: A "simple environment" refers to a sample with low host-DNA contamination, high microbial load, and typically well-characterized. An example would be DNA extracted from healthy human stool.
What characterize a sample from a “complex environment”?
- A: A "complex environment" refers to a sample that either has an extremely high microbial load, which would benefit from higher sequencing coverage (e.g., environmental samples), or a sample with higher or unknown host-DNA contamination and lower microbial load, such as diarrhea samples, skin samples, or other intestinal-based samples.
- What is the minimum percentage of host-DNA contamination present within a sample that we can accept?
- A: We recommend that the host DNA contamination be ≤50% per sample (per total reads), especially for shotgun metagenomic sequencing with a lower sequencing depth.
Why is shotgun metagenomic sequencing with lower sequencing depth more susceptible to the effects of host DNA contamination?
- A: In the presence of host DNA contamination, we typically need to remove the host DNA reads from the sequenced data. If the contamination is high, a large percentage of reads will be removed, potentially leaving an insufficient amount of data for further analysis.
- Can a customer with metagenomic samples containing high host-DNA contamination still proceed with deep shotgun metagenomic sequencing?
- A: For samples with high host-DNA contamination (≥50%), it usually indicates a low microbial load. In extreme cases, host-DNA contamination can be as high as 99%, leaving only 1% microbial DNA, meaning most of the sequenced data will not yield viable microbial results.
While deeper sequencing (≥12 Gb) may increase the amount and resolution of microbial data, it won't change the proportion of host to microbial DNA. In such cases, amplicon sequencing may be suggested, as it can filter out host DNA. However, please note that amplification may fail if there isn’t enough microbial DNA in the sample. It's important to inform the customer about the risks associated with both methods when working with samples containing high levels of host-DNA contamination.
- What is the difference between the NR database and the microNR database for assembly-based analysis?
- A: By default, we use the microNR database, which contains only microbiome species information. If the customer is interested in studying viruses, fungi, or other eukaryotes, they should request the "NR database" in the quotation. While there is no additional charge for using the NR database, it may extend the turnaround time by 2-5 working days due to the larger size of the database.
Analysis MethodShotgun Metagenomics Assembly-BasedShotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)Shotgun Metagenomics Reads-Mapping (Kraken2)PositioningMore comprehensive research needs for both genomic composition, taxonomy composition and function of microbial communities.Species-Function AssociationHost-association studiesAntimicrobial-based researchHuman/Animal/Environmental based studies.Limited fundsSensitive Turnaround TimeLarge cohort studiesBetter classification accuracy but do not need genome sequence or reconstruction of colony genesHuman/Animal based microbiome studiesClinical/treatment focused researchLimited fundsSensitive Turnaround TimeLarge cohort studiesBetter classification accuracy but do not need genome sequence or reconstruction of colony genesInterested in viruses and protists annotation.Environmental samples especially customers initially interested in customizedamplicon sequencing.Analysis MethodShotgun Metagenomics Assembly-BasedShotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)Shotgun Metagenomics Reads-Mapping (Kraken2)PositioningMore comprehensive research needs for both genomic composition, taxonomy composition and function of microbial communities.Species-Function AssociationHost-association studiesAntimicrobial-based researchHuman/Animal/Environmental based studies.Limited fundsSensitive Turnaround TimeLarge cohort studiesBetter classification accuracy but do not need genome sequence or reconstruction of colony genesHuman/Animal based microbiome studiesClinical/treatment focused researchLimited fundsSensitive Turnaround TimeLarge cohort studiesBetter classification accuracy but do not need genome sequence or reconstruction of colony genesInterested in viruses and protists annotation.Environmental samples especially customers initially interested in customizedamplicon sequencing.What is the positioning between assembly-based analysis and reads-mapping based (MetaPhlAn4-HUMAnN3) analysis? A:
Analysis Method
Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Shotgun Metagenomics Reads-Mapping (Kraken2)
Positioning
More comprehensive research needs for both genomic composition, taxonomy composition and function of microbial communities.
Species-Function Association
Host-association studies
Antimicrobial-based research
Human/Animal/Environmental based studies.
Limited funds
Sensitive Turnaround Time
Large cohort studies
Better classification accuracy but do not need genome sequence or reconstruction of colony genes
Human/Animal based microbiome studies
Clinical/treatment focused research
Limited funds
Sensitive Turnaround Time
Large cohort studies
Better classification accuracy but do not need genome sequence or reconstruction of colony genes
Interested in viruses and protists annotation.
Environmental samples especially customers initially interested in customized
amplicon sequencing.
Analysis Method
Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Shotgun Metagenomics Reads-Mapping (Kraken2)
Positioning
More comprehensive research needs for both genomic composition, taxonomy composition and function of microbial communities.
Species-Function Association
Host-association studies
Antimicrobial-based research
Human/Animal/Environmental based studies.
Limited funds
Sensitive Turnaround Time
Large cohort studies
Better classification accuracy but do not need genome sequence or reconstruction of colony genes
Human/Animal based microbiome studies
Clinical/treatment focused research
Limited funds
Sensitive Turnaround Time
Large cohort studies
Better classification accuracy but do not need genome sequence or reconstruction of colony genes
Interested in viruses and protists annotation.
Environmental samples especially customers initially interested in customized
amplicon sequencing.
Why are we currently primarily accepting human/animal-based stool and gastrointestinal-based (GI-based) samples for MetaPhlAn4-
HUMAnN3 analysis pipeline?
- A: The MetaPhlAn and HUMAnN software, along with their corresponding databases, were originally developed for the Human Microbiome Project. Consequently, this analysis pipeline is particularly well-suited for human and animal-based microbiome studies, especially large cohort studies. The software and databases may not be as suitable for environmental studies.
Analysis MethodShotgun Metagenomics Assembly-BasedShotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)Shotgun Metagenomics Reads-Mapping (Kraken2)SummaryTraditional macro genome analysis methods, through the construction of DBG graphical mapping method to get Contig, gene prediction to get the gene set.Through the gene set of the comparison to get the annotation results of species and functions.Skip assembly and gene prediction, directly use raw reads to compare with reference database or reference characterized genome to get species/function annotation resultsSkip assembly and gene prediction, directly use raw reads to compare with reference database or reference characterized genome to get species/function annotation resultsAnalysis MethodShotgun Metagenomics Assembly-BasedShotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)Shotgun Metagenomics Reads-Mapping (Kraken2)SummaryTraditional macro genome analysis methods, through the construction of DBG graphical mapping method to get Contig, gene prediction to get the gene set.Through the gene set of the comparison to get the annotation results of species and functions.Skip assembly and gene prediction, directly use raw reads to compare with reference database or reference characterized genome to get species/function annotation resultsSkip assembly and gene prediction, directly use raw reads to compare with reference database or reference characterized genome to get species/function annotation resultsWhat are some of the main differences between our assembly-based and reads-mapping analyses pipeline? A:
Analysis Method
Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Shotgun Metagenomics Reads-Mapping (Kraken2)
Summary
Traditional macro genome analysis methods, through the construction of DBG graphical mapping method to get Contig, gene prediction to get the gene set.
Through the gene set of the comparison to get the annotation results of species and functions.
Skip assembly and gene prediction, directly use raw reads to compare with reference database or reference characterized genome to get species/function annotation results
Analysis Method
Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Shotgun Metagenomics Reads-Mapping (Kraken2)
Summary
Traditional macro genome analysis methods, through the construction of DBG graphical mapping method to get Contig, gene prediction to get the gene set.
Through the gene set of the comparison to get the annotation results of species and functions.
Skip assembly and gene prediction, directly use raw reads to compare with reference database or reference characterized genome to get species/function annotation results
Advantages
Predicted genes: obtain unknown species.
Species and function are mediated through gene sets.
Know which function is produced by which species.
Contain bacteria, archaea, fungi, protists and viruses.
Suitable for all types of
samples (microbiome and environmental).
Antibiotic resistant gene annotation and analysis
Not dependent on assembly quality
More stable and accurate quantification
Fast TAT while providing accurate profiling results.
- Can work with smaller data size compared to assembly-based. (1Gb+)
Contain bacteria, archaea and fungi.
Human/Animal Microbiome Samples
More accurate compared to Kraken2
Not dependent on assembly quality
More stable and accurate quantification
Fast TAT while providing accurate profiling results.
- Can work with smaller data size compared to assembly-based. (1Gb+)
Contain bacteria, archaea, fungi, viruses and protists.
Suitable for complex samples (microbiome and
environmental).
Viruses’ annotation will be easier when compared to assembly-based.
Disadvantages
Sample complexity and species complexity can have an impact on assembly results.
Dependent on assembly results.
Higher computational cost and
longer TAT.
No gene information.
No species to function correspondence.
No viruses and protists information.
No gene information.
No species to function correspondence.
More false positives compared to MetaPhlAn4
Why is it easier to annotate viruses and protists through Kraken2 as opposed to the assembly-based analysis method?
- A: Viral genomes are typically small, whereas the genomes of protists are generally larger and more complex than those of bacteria. This complexity poses greater challenges during the assembly process, often leading to suboptimal assembly outcomes for these types of microorganisms. Since gene prediction depends on successful genome assembly, which is then used for downstream taxonomy annotation, obtaining accurate taxonomy results for viruses and protists can be particularly difficult.
In contrast, Kraken2 employs a read-mapping approach that directly annotates reads against various databases, effectively bypassing the assembly step. This enables Kraken2 to provide more accurate annotation results for viruses and protists.
- Note:
* If a customer wishes to use Kraken2 for taxonomy annotation of viruses or protists, please contact the project manager in advance to request the PlusPFP database. Since the PlusPFP is larger than the standard Kraken2 database, projects utilizing it for taxonomy annotation will require additional turnaround time (TAT).
- How is normalization performed for heatmaps?
- A: The data within the cluster heat map is the Z value. The Z-value is defined as the difference between the relative abundance of a sample on that species and the average relative abundance of all samples on that taxonomy divided by the average relative abundance of all samples on that taxon. Standard deviation of the resulting value is Z = (X - µ) / σ. When the relative abundance of a species in a sample is lower than the average of all samples in this species, the Z value is negative, and vice versa. The greater the difference between the relative abundance and the mean, the closer the value is to 1 or -1.
What differences are between the three dimensionality reduction methods of PCA, NMDS, and PcoA; and which one is better?
- A: The purpose of dimensionality reduction is to sort the target data on a low-dimensional plane with the help of dimensionality reduction.
Principal Component Analysis (PCA): A dimensionality reduction analysis based on a linear model that assumes that species abundance responds to a linear change along with changes in environmental variables. This is also a limitation of PCA.
Principal Co-ordinates Analysis (PcoA): the distance between samples is projected at different angles on the coordinate axis, and the first two coordinate axes that best reflect the original distance distribution are found for data output.
Non-metric Multi-Dimensional Scaling analysis: NMDS analysis uses non-linear distances (which is different from PCA), and the degree of difference between different samples is displayed as the distance between points and points, which can reflect the differences between or within a group of samples.
In short, regarding the dimensionality reduction method, there isn’t the best method but only the most appropriate to the customer’s
research interest.
- Can we provide mobile genetic element (MGE) annotation results?
- A: Yes, MGE (transposons, integron and plasmids) annotation and analysis results are provided in our assembly-based standard analysis.
Long Reads Shotgun Metagenomics (PacBio)
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity
PacBio DNA HiFi library
HMW* Genomic DNA
(Metagenomics)
≥ 5.5 μg**
≥ 50 μL
≥ 70 ng/μL
OD260/280=1.75~2.0 OD260/230=1.3~2.6
NC/QC***=1.0~2.2
Fragments should be ≥ 20K
- Note:
*HMW: High Molecular Weight.
**≥ 5.5 μg: The recommended sample amount for PacBio HiFi library is ≥5.5μg. (Additional 5 ug per sample per cell is needed.)
***NC/QC: NanoDrop concentration/Qubit concentration Recommended suspension buffer: EB
Sequencing Strategy and Turnaround Time
Application
Library Type
Recommended Sequencing Depth*
Turnaround Time (≤ 6 sample)
WOBI
WBI
Metagenomics
HiFi library
10-15Gb HiFi data
30
45
- Note:
*The minimum order of HiFi sequencing is one Cell. If the required data amount is lower than the output of one cell, please reach out to the APM team for further evaluation.
4. FAQ
- Can we perform HMW DNA extraction for metagenomic samples?
- A: Sorry, currently we can’t provide HMW DNA extraction. Here are some recommended kits for help: Circulomics / Qiagen Gentra Puregene / Qiagen MagAttract HMW DNA extraction kits. PacBio also provides official recommendations. Here is the link: https://extractdnaforpacbio.com
- Can we order less than 1 cell for long reads shotgun metagenomic sequencing with PacBio？
- A: No, the minimum order will be 1 cell. If the customer’s required data amount is lower than the output of one cell, please still order one cell. To reduce the costs, customers can appropriately pool their samples within one Cell
- Can we provide English analysis report for our long-reads shotgun metagenomic sequencing with PacBio?
- A: Not at the moment, the English analysis report is currently in development and it is expected to go live officially by the end of June, 2025.
Is the assembled metagenome through our long-reads shotgun metagenomic sequencing with PacBio analysis considered MAGs?
- A: No, the assembled metagenome has only gone through a more accurate assembly but did not go through a binning process, so that is why the assembled metagenomes are not considered as MAGs.
Long Read Shotgun Metagenomic Sequencing (Nanopore)
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity
Nanopore PromethION DNA
library
HMW* Genomic DNA (Metagenomics)
≥ 5.5 μg
≥ 50 μL
≥ 80 ng/μL
OD260/280=1.7~2.5; OD260/230=1.1~2.6; NC/QC**=0.95~4.00
Fragments should be ≥10K
- Note:
*HMW: High Molecular Weight.
**NC/QC: NanoDrop concentration/Qubit concentration
Sequencing Strategy and Turnaround Time
Application
Recommended Sequencing Depth
Turnaround Time (≤ 20 sample)
WOBI
WBI
Metagenomics
10Gb Nanopore data+10Gb Illumina data*
30
40
Note
*≥ 10Gb of Illumina data is required if the customer is interested in doing WBI analysis with us.
Analysis Contents
Standard Analysis Metagenomics*
Software
Data quality control
NanoPlot
Metagenome assembly
Flye
Gene prediction and abundance analysis
MetaGeneMark
Species annotation (MicroNR)
DIAMOND
Function annotation and function abundance analysis
-KEGG, eggNOG, CAZy
-Anosim analysis
-Metabolic pathway analysis
-Metastat analysis
-LEfSe analysis
DIAMOND
Metastats
Resistance gene annotation (CARD)
Resistance Gene Identifier
## FAQ
- Can we offer HMW DNA extraction services for bacteria or metagenome samples?
- A: We don’t have HMW DNA extraction services currently. However, we can recommend some kits that may be helpful: Circulomics/ Qiagen Gentra Puregene/ Qiagen MagAttract HMW DNA extraction kits. Additionally, Oxford Nanopore provides an official community offering extensive support, including extraction protocols for various species and sample types. When receiving inquiries, please first confirm the species and sample type with the customer, then visit the community to find the appropriate protocols. The community is open for registration to those interested in Nanopore sequencing. You can access it here: https://community.nanoporetech.com/docs/prepare/extraction_protocols?from=support.
Do we have any analysis services for metagenomics samples?
- A: Currently, we only offer the Chinese version for bacterial complete map and metagenomics analysis. The English version is under development and is expected to be available by the end of 2024. For customers who can accept the Chinese report, these services are available. For other important or large projects that require the English version, please consult with the APM team.
- Can analysis proceed without the Illumina 10Gb sequencing requirement?
- A: No. Our hybrid analysis pipeline requires both short-read (Illumina) and long-read (nanopore) data. Customers must purchase the 10Gb NGS-based shotgun metagenomic sequencing service to enable this integrated analysis approach.
- What is the current data output files?
- A: POD5 format. Due to the latest version on ONT’s instrument software no longer supporting demultiplexing of FAST5 data as mentioned in the Nanopore Product manual, we will primarily provide POD5 data to the customer. POD5 data and FAST5 contain the same information but in different format and the customer can convert POD5 to FAST5 format if needed. However, if the customer explicitly requests for FAST5 data during data release, additional conversion fees may apply. Please reach out to the APM team for more information.
Novogene Product Manual
Amplicon Metagenomic Sequencing
AMEA 2025.05
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director. If you have any questions about the products, please consult the APM team.)
Product Manual Revisions
Subject
Novogene Product Manual-7 Amplicon Sequencing Product Manual-2025 V1.0
Revision Number
2025 V1.0
Issue Date
May 31st, 2025
Prepared by
Chen Yu
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2024 V1.0
Pg 4-Battle Card Update
Pg 7-Analysis Content Comparison Update Pg 8-(Amplicon): DNA extraction update
Pg 10-(Amplicon): Sequencing strategy and turnaround time Pg 16-(Amplicon) FAQ 1: Example Questions
Pg 20-(Amplicon) FAQ 3: Multiple amplification regions sample requirements Pg 21-(Amplicon) FAQ 5: Amplicons exceed 470bp
Pg 24-(Amplicon) FAQ 9: Quoting customized primers Pg 25-(Amplicon) FAQ 11: PE250 to PE256.
Pg 26-(Amplicon) FAQ 12-13: PE250 going forward and PE256 data release Pg 27-(Amplicon) FAQ 14: Phased nucleotides
Pg 28-(Amplicon) FAQ 15-16: Reads merging and PE250 data requests Pg 29-(Amplicon) FAQ 18: Customized databases for taxonomy annotation Pg 34-(Amplicon) FAQ 29: Software options for function prediction
Pg 36-(PCR Products): Sequencing strategy and Analysis contents Pg 37-(PCR Products) FAQ 1: PCR products checklist
Pg 38-(PCR Products) FAQ 2: Adapters’ impact on PCR products Pg 39-(PCR Products) FAQ 3: Information on
Pg 40-(PCR Products) FAQ 4: Metabarcoding PCR products only Pg 40-(PCR Products) FAQ 6: PCR products exceed 470 bp
Pg 40-(PCR Products) FAQ 12-15: PE250 to PE256 and its impact
Pg 43-(PCR Products) FAQ 16-17: PE256 data release and demultiplexing
Pg 44-(PCR Products) FAQ 19-20: Standard analysis and customized databases
Chen Yu
Oct 31st, 2024
2025 V1.0
Pg 48- Added PacBio Full Length 16S Sequencing complete content Pg 48-(PacBio) Sample Requirements Note
Pg 49-(PacBio) FAQ 1: DNA extraction
Pg 51-(PacBio) FAQ 5: Amplification primer sequence
Chen Yu
May 31st, 2025
Contents
Microbial Solutions: Metagenomic Samples Battle Card6
Comparison Chart:6
Analysis Content Comparison9
Amplicon Sequencing10
DNA extraction10
## Sample Requirements11
Sequencing Strategy and Turnaround Time12
Analysis Contents12
Demo for Data Release Structure15
## FAQ18
Amplicon Sequencing with PCR Products37
## Sample Requirements37
Sequencing Strategy and Turnaround Time37
Analysis Contents38
Demo for Data Release Structure38
## FAQ39
PacBio Full-Length 16S Sequencing48
## Sample Requirements48
Sequencing Strategy and Turnaround Time48
Analysis Contents49
Data delivery49
## FAQ49
Microbial Solutions: Metagenomic Samples Battle Card
Comparison Chart:
Product Types
Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Amplicon Sequencing
16S Full-length Amplicon Sequencing
PCR Product/ Customized Amplicon Sequencing
## Sample Requirements
DNA amount
≥100ng,
DNA volume ≥ 20 µl.
DNA amount
≥100ng
DNA volume ≥ 20 µl.
DNA amount ≥ 200ng,
DNA volume ≥ 20 µl.
DNA amount ≥ 300ng, Concentration ≥ 10ng/ µl
DNA amount ≥
1.5µg
DNA volume ≥ 20 µl
Sample Types
Human Environmental, Bacteria
Animal and Plants
Human, Animal*
Human Environmental, Bacteria,
Animal and Plants
Human Environmental, Bacteria,
Animal and Plants
Human-based, Environmental, Bacteria
Animal and Plants
Data Requirement
6-12Gb+
3-12 Gb+
100K raw tags
20-40K clean reads
1M raw reads (no barcodes) or
100k raw tags (with
barcodes）
Sequencing Platform
Illumina Novaseq PE150
Illumina NovaSeq 500 Cycles
PacBio
Illumina NovaSeq 500 Cycles*
Taxonomic Resolution
Species/Sub-species level
Species-Level
Genus Level (Limited Species-Level)
Species/Sub-Species Level
Genus Level (Limited Species-Level)
Taxonomic Coverage
All Taxa
All taxa
Amplification region Specific
Bacteria and Archaea (16S)
Amplification region Specific
Genome Reconstruction
Yes
No
Databases
K-mers (Scaftigs)
Marker Genes
Ribosomal Genes
Marker Genes
Taxonomy Annotation
Micro_NR / NR database
MetaPhlAN4/ HUMANn3
Qiime1/Qiime2
Qiime2
Qiime1/Qiime2
Function Annotation
KEGG, eggnog, CAZy, PHI, VFDB
MetaCyc, KEGG, GO, eggnog, Pfam
No
Antibiotic Resistance Annotation
CARD, Integrall, isfinder, Plasmid
No
Amplicon contamination
No
Yes
Host DNA Contamination
High (sample type-dependent, requires host removal)
High (sample type-dependent, requires host removal) **
Low
- Note:
* For PCR Products and customized amplicons, the majority of samples are still being sequenced on PE256. However, there are exceptions and we do accept samples for PE150 as well. Please submit an inquiry to the APM team for more clarification if needed.
** Reads-Mapping based shotgun metagenomic sequencing is very susceptible to host contamination and we will need the customer to provide us with samples with less than 50% of host contamination within the total raw reads. At the moment, our MetaPhlAn-HUMAnN pipeline is better suited for gut and fecal related samples.
Analysis Content Comparison
Product Types
Shotgun Metagenomics Assembly-Based
Shotgun Metagenomics Reads-Mapping (MetaPhlAn4-HUMAnN3)
Amplicon Sequencing
Analysis Similarities
Taxonomic Annotation
- Alpha Diversity
Beta Diversity analysis
- Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Taxonomic Annotation
- Alpha Diversity
Beta Diversity analysis
- Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Taxonomic Annotations Alpha Diversity
Beta Diversity analysis
- Statistics and group comparison analyses (MetagenomeSeq, LEFSe)
Analysis Differences
- Metagenome Assembly
- Gene Prediction
- Function Annotation
- Antibiotic Resistance Gene Annotation
- Function Annotation
- Function Prediction*
- Environmental Association Analyses**
- Network Analysis**
- Note:
* One round of function prediction is part of the standard analysis for Qiime2 but it is also considered a part of our advance analysis for both Qiime1 and Qiime2.
** Environmental association analyses and network analysis are part of the advance analyses for both Qiime1 and Qiime2 in Amplicon Sequencing.
Amplicon Sequencing
16S/18S/ITS amplicon sequencing is frequently used to identify and differentiate microbial species. Short (<500bp) hypervariable regions of conserved genes or intergenic regions, such as 16S of bacteria and archaea or 18S/ITS of fungi, are amplified by PCR and analyzed using next-generation sequencing (NGS) technology. The resulting sequences are compared against microbial databases. Applications range from characterizing the microbiota of animals or plants, to comparing species diversity and population structure from various environmental sources or geographic regions. In short, the goal of amplicon sequencing is to meta-barcode the microorganisms present within a mixed sample.
DNA extraction
Sample types*
Species
Recommended Input
Replicates**
Tube Recommendations
Transportation
Stool
Human/Animal
≥ 2ml
2
DNA shield reagent or Invitek Stool collection tube
Follow tube specification
Stool (Qiagen)
(96 samples at a time required) ***
Human
˃ 250mg
3
1.5ml Eppendorf tube
Dry Ice
Saliva
Human
≥ 4ml
2
Oragene DNA Collection tube (DNA Genotek)
Ice Bag
Buccal Swabs/ Tongue Swab/ Mouth/ Cheek
Human
≥ 4
Don’t put lysis buffer
2
Sterile, pre-cooled 1.5/2.0ml EP tube
Dry Ice
Soil/ Sludge****
NA
Transfer to a microcentrifuge tube
3
1.5ml Eppendorf tube
Room temperature
- Note:
Please check with the APM team on kit availability for any projects that will need DNA extraction in SG lab for sample numbers over 50 samples.
For more details, refer to the Sample Extraction Services in the price list.
** Replicates are very necessary for DNA extraction, please confirm with the customer that their samples can meet the number of replicates needed for DNA extraction. If the customer is unable to meet our sample requirements, please reach out to the APM team for an evaluation.
*** Stool DNA extraction using Qiagen kit requires 96 samples at a time so we recommend customers to send samples in multiples of 96 samples. We do not accept samples that are less than 96 samples at a time. Please also reach out to the APM ahead of time with the information of when customers plan to send in their samples and their sample number.
**** For sludge samples or any sediment samples that are high in water content, please have the customer spin down their samples and provide only the spun down solids to us for DNA extraction. For more details, please reach out to the APM team for an evaluation.
## Sample Requirements
Sample Type
Sources/Remarks
Amount
Volume
Concentration
Purity (NanoDropTM/ Agarose Gel)
Total DNA
Soil, feces, Intestines, plants, animal tissues*, etc.
≥ 200 ng*
≥ 20 μL
≥ 10 ng/μL
OD260/280 = 1.8-2.0,
No degradation, no contamination, no color
- Note:
Please refer to FAQ 3 for more information on sample requirement when customer would like to amplify more than one region from the same sample.
Sequencing Strategy and Turnaround Time
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 36 samples)
WOBI
WBI
NovaSeq 500 Cycles*
100k tags/sample
26 working days
32 working days
NovaSeq 500 Cycles
1M raw reads/library
26 working days
32 working days
- Note:
The sequencing strategy for amplicon sequencing is now known officially as NovaSeq 500 Cycles. This includes the use of PE256 due to the recent update that replaces our previous PE250 sequencing strategy as PE256. Please refer to FAQ 11-16 more information
Analysis Contents
Standard Analysis (Qiime1)
Software
Data split and reads merging
Cutadapt, FLASH
Data quality control: data filtration and chimera removal
Fastp, Vsearch
Taxonomic analysis:
Clustering-OTUs (Operational Taxonomic Units), phylogenetic tree, Taxonomy annotation (16S/18S: Silva138, ITS: Unite v8.2), Relative abundance bar graph, Cluster heatmap, Ternary plot, Evolutionary tree, Venn and Flower diagram.
Uparse, Qiime, muscle, R, perl
Alpha-Diversity Analysis:
Alpha Indices table (Observed species, good coverage, Chao1, ACE, Shannon, Simpson, PD whole tree), Rarefaction curves, Species accumulation box plot, Rank abundance curves, Alpha diversity indices differences box plot.
QIIME, R
Beta-Diversity Analysis:
Beta diversity heatmap, UPGMA (Unweighted Pair-group Method with Arithmetic Means), PCA (Principal Component Analysis), PCoA (Principal Co-ordinates Analysis), NMDS (Non-Metric Multidimensional Scaling).
QIIME, R, perl
Community Difference Analysis:
Anosim, MRPP, Adonis, Simper, Species T-test analysis, Metastats, LEfSe analysis
R, LEfSe
Standard Analysis (Qiime2)
Software
Data split and reads merging
FLASH
Data quality control: data filtration and chimera removal
Fastp, Vsearch
Taxonomic analysis:
denoise-ASVs (DADA2/deblur, default: DADA2), Taxonomy annotation (16S/18S: Silva138, ITS: Unite v8.2), Relative abundance bar graph, Cluster heatmap, Ternary plot, Evolutionary tree, Venn and Flower diagram.
QIIME2
Alpha-Diversity Analysis:
Alpha Indices table (Observed species, good coverage, Chao1, ACE, Shannon, Simpson, PD whole tree), Rarefaction curves, Species accumulation box plot, Rank abundance curves, Alpha diversity indices differences box plot.
QIIME2, R
Beta-Diversity Analysis:
Beta diversity heatmap, UPGMA (Unweighted Pair-group Method with Arithmetic Means), PCA (Principal Component Analysis), PCoA (Principal Co-ordinates Analysis), NMDS (Non-Metric Multidimensional Scaling).
QIIME2, R, perl
Community Difference Analysis:
Anosim, MRPP, Adonis, Simper, Species T-test analysis, Metastats, LEfSe analysis
R, LEfSe
Function Prediction Analysis (Select one) *
PICRUSt, PICRUSt 2, Tax4Fun, FAPROTAX, FunGuild, BugBase
picrust, picrust2, tax4fun, python, R
- Note:
Please note that our Function Prediction only covers the regions 16S and ITS regions but not 18S and other customized regions.
Analysis Type
Content of Advanced Analysis
Minimum Sample Requirement
Software
Price (USD)*
TAT (d)**
Environmental Association Analysis***
Spearman, CCA/RDA, dbRDA
≥ 3 samples
R
50-60/case
1
Spearman, CCA/RDA, dbRDA + Mantel
≥ 3 samples
R
65-75/case
1
Spearman, CCA/RDA, dbRDA + VPA
≥ 3 samples
R
65-75/case
1
Spearman, CCA/RDA, dbRDA + Mantel + VPA
≥ 3 samples
R
80-90/case
1
Association Analysis
Network Analysis
≥ 6 samples
R
50-60/case
1
Function Prediction***
PICRUSt2, PICRUSt, Tax4Fun, Faprotax, FUNGuild,BugBase
≥ 3 samples (Bugbase)
PICRUSt2, PICRUSt,
Tax4Fun, Faprotax, FUNGuild,BugBase
60-80/case
1
Customized***
Krona Analysis
Perl
50-60/case
1
- Note:
The pricing for advanced analysis is cumulative.
If the customer provides a completed BI form that includes both standard and advanced/customized analysis from the outset, they will receive a 20% discount on advanced/customized analysis.
** Additional turnaround time will not be cumulative if the customer provides a completed BI form with both standard and advanced/customized analysis included.
*** For guidance on quoting customized analysis requests, especially when multiple function predictions are required, please refer to FAQs 20-23.
Demo for Data Release Structure:
WOBI:
- Note:
Due to the differences in OTUs and ASVs within the merged analysis pipeline, we no longer offer the summarization of tags and OTU number for each sample within the report. This information is only provided within the data release for Qiime1 instead.
- Note:
1 round of Function Prediction analysis with any software is part of the standard analysis for Qiime2. However, if the customer would like to add more than one round of Function prediction, please refer to the additional pricing found under advanced analysis.
WBI (Qiime1 and 2 Standard and Advance Analysis):
## FAQ
What key questions should be asked when a customer expresses interest in amplicon sequencing using gDNA?
- A: Please see the table below for sample questions to consider when addressing new amplicon sequencing inquiries from customers.
Question Types
Questions to Ask the Customer
Follow-up Clarification Questions
Possible Solutions
Research-Based Questions
Q1. Have they done any projects previously with us?
Yes, to Q1.1; No, to Q2.
Q1.1 Do they wish to analyze this batch of samples with previous analysis pipelines for either Qiime1/Qiime2? Or do they require re-analysis alongside previous samples?
Yes, to A1.1; No, to A1.2.
A1.1 Please remark in Quotation and let the project managers to use the previous analysis pipelines for either Qiime1/Qiime2. Please do not apply the newly merged analysis pipeline for this customer type.
A1.2 You can recommend the newly merged analysis pipeline, however, the result can’t be compared with previous results.
Q2. Are they interested in identifying species down to the species level? Yes, to Q2.1; No, to Q3.
Q2.1 What type of sample and species is the customer looking to identify?
A2. Based on the sample type, target species, and budget considerations, we recommend the customer explore either 16S full-length amplicon sequencing or shotgun metagenomics.
Q3. Are they interested in studying the interactions between different species within the sample?
Yes, to Q3.1; No, to A3.3.
Q3.1 Does the customer have any budget or sample constraints?
No, to A3.1; Yes, to A3.2.
A3.1 Shotgun metagenomics is generally recommended for studying species interactions as it can provide more functional information.
A3.2 Please recommend the customer to consider advanced analyses using Qiime1/Qiime2.
A3.3 Please proceed with amplicon
sequencing.
Amplification-based Questions
Q4. Do they have a specific amplification region in mind for their samples?
Yes, to Q4.1; No, to A4.1.
Q4.1 Would the customer be open to using our standard amplification regions?
* Yes, to A4.1; No, to A4.2.
A4.1
Our standard amplification regions are:
16S: for bacteria/archaea
ITS: for fungi
18S: for eukaryotes (including fungi) A4.2 If not, consider using customized primers. For more information, please refer
to FAQ 8 and 9.
Q5. For customized primers, can the customer provide the primer sequences and the expected amplicon size? Yes, to Q5.1; No, to Q5.2
Q5.1 Does the customer require analysis using a different database?
No, to A5.1; Yes, to A5.2.
Q5.2 Can the customer provide a reference article?
Yes, to A5.2; No, to A5.3.
A5.1 The expected amplicon size should be within 200-470bp. Please see FAQ 4-6 for more information.
A5.2 Please submit inquiry to APM with the specified database/ article for evaluation.
A5.3 Recommend our standard amplification
regions or metagenomics as alternatives.
Q6. Do they require amplification of more than one region for their samples?
Yes, to A6.1; No, to A6.2
-
A6.1 Please refer to FAQ 3 for the sample requirements when amplifying multiple regions.
A6.2 Please proceed with our standard sample requirements.
Q7. Do they need DNA extraction?
Yes, to Q7.1; No, to A7.3
Q7.1 Are the samples in the DNA extraction list?
Yes, to A7.1; No, to A7.2.
A7.1 Please review the DNA extraction sample requirements.
A7.2 Please submit an inquiry with details pretreatment of the samples/ tissues.
A7.3 Please proceed with our standard sample requirements.
A8.1 Please note this in the quotation and
instruct the project managers to use the
previous analysis pipelines (Qiime1/Qiime2).
Q8. Do they need analysis?
Yes, to Q8.1; No, to A8.3.
Q8.1 Do they need to conduct joint analysis with previous projects?
Yes, to A8.1; No, to A8.2
Please do not apply the newly merged analysis pipeline for this customer type. A8.2 You may recommend the newly
merged analysis pipeline; however, the
results will not be directly comparable to
previous data.
A8.3 Please proceed with WOBI projects.
A9.1 Recommend Qiime2, as one round of
function prediction is included in the
Analysis-based Questions
Q9. Do they need function prediction?
Yes, to Q9.1; No, to A9.3
Q9.1 Is the function prediction method the customer is interested in included in the BI Form?
Yes, to A9.1; No, to A9.2
standard Qiime2 analysis. **
A9.2 Please submit an inquiry with details method which the customer is interested in. A9.3 Both Qiime1 and Qiime2 are suitable. If the customer has no preference, we
recommend Qiime2 as it is the more up-to-
date software.
Q10.Do they need any advanced analysis?
Yes, to Q10.1; No, to
A10.2
Q10.1 The customer’s sample types and research focus may provide relevant insights. Proceed to A10.1.
A10.1 Please quote the various advanced analysis under “customized analysis” and provide clear details in the “Customized Analysis Note” for any of the desired analyses.
A10.2: Please proceed with our standard
analysis.
Q11. Do they require the data in PE250 format instead of PE256?
Yes, to A11
This applies only to projects where the customer has explicitly requested consistency with previous batches.
Novogene typically offers PE256 sequencing, and PE256 is the default format for most amplicon sequencing projects.
A11. Please inform the project managers in advance so that the bioinformatics team can trim the data to PE250 format. For further details, please refer to the FAQ 16.
- Note:
* Please refer to FAQ7 for our list of standard amplification regions.
** If the customer wishes to include more than one round of function prediction, please consult the additional pricing under advanced analysis and refer to FAQs 22-23 for further details.
- How to ship tissue samples from overseas?
- A: If the tissue sample type is included in our extraction list, the client can ship the tissue samples directly. All tissue samples must be flash-frozen using liquid nitrogen and shipped on dry ice.
For tissue samples not listed in the extraction list, please contact the Product Manager and logistics team for guidance on shipping and extraction inquiries.
- What is the sample requirement for the samples that need to be amplified multiple times for different amplicon regions?
- A: When a sample requires amplification across multiple regions, the sample requirements are cumulative. For example, if a soil sample needs amplification for both the 16S V4 and ITS1 regions, the minimum sample requirement is m ≥ 400 ng, with a concentration of C ≥ 10 ng/μL. Additionally, 3 replicates per sample are required for each region, though 5 replicates are strongly recommended for optimal results.
If the customer is interested in studying more than one amplification region, they may also consider shotgun metagenomic sequencing. This method sequences the total gDNA in the mixed sample, allowing for comprehensive comparison across microbial species from different taxa (e.g., bacteria and fungi), which is not possible with amplicon sequencing.
Why must the amplicon region size be no more than 470bp？
- A: During analysis, the two reads are merged into a single tag using a 15bp overlap. To ensure successful merging for sequencing with PE250, the amplicon region size must be no more than 470bp, allowing for a sufficient 10-15bp overlap between the reads.
What happens when the expected amplicon exceeds 470bp?
- A: We do not accept amplicons exceeding 470bp, as this compromises our ability to perform PCR-free library preparation and results in suboptimal outcomes during the read-merging process.
What happens when the expected amplicon is less than 200bp?
- A: If the expected amplicon is under 200bp, it will need to be sequenced using PE150. Please note that we cannot accept amplicons (PCR products) shorter than 100bp, as the short length leads to excessive adapter reads and results in suboptimal sequencing data for the customer.
- How do we define the difference between our standard primers and customized primers?
- A: Any primer sequence or amplification region not included in the list below is considered a customized primer, which will incur additional charges for primer synthesis and amplification using the customized primer.
Standard Primer List：
Region
Amplified Region
Fragment Length
Primers
Sequences (5’-3’)
Bacterial 16S
V3-V4
470 bp
341F
CCTAYGGGRBGCASCAG
806R
GGACTACNNGGGTATCTAAT
V4
300 bp
515F
GTGCCAGCMGCCGCGGTAA
806R
GGACTACHVGGGTWTCTAAT
V4-V5
450 bp
515F
GTGCCAGCMGCCGCGGTAA
907R
CCGTCAATTCCTTTGAGTTT
V5-V7
(for endophytic)
435 bp
799F
AACMGGATTAGATACCCKG
1193R
ACGTCATCCCCACCTTCC
Archaeal 16S
Archaea V4 (AKA. Novel Archaea
V4)
415 bp
519F
CAGCCGCCGCGGTAA
915R
GTGCTCCCCCGCCAATTCCT
Eukaryotic 18S
V4
350 bp
528F
GCGGTAATTCCAGCTCCAA
706R
AATCCRAGAATTTCACCTCT
Fungal ITS
ITS2
320-380 bp
ITS3
GCATCGATGAAGAACGCAGC
ITS4
TCCTCCGCTTATTGATATGC
ITS1-5F
200-400 bp
1737F
GGAAGTAAAAGTCGTAACAAGG
2043R
GCTGCGTTCTTCATCGATGC
ITS1-1F
(for endophytic)
200-400 bp
ITS1F
CTTGGTCATTTAGAGGAAGTAA
ITS2
GCTGCGTTCTTCATCGATGC
Customized Primer price:
- A: (1) If the primer is included in our standard primer list (FAQ 7), there is no additional charge for primer synthesis or amplification.
(2) If the primer is not on our standard primer list (FAQ 7), and the length of the primer pair (F and R) is between 50-60bp without containing U or I base, the primer synthesis prices are as follows: (Novogene does not provide this service for genotyping primers).
For 1-4 samples: we do not accept less than 5 samples
For 5-9 samples: $18-20 USD/sample
For 10-24 samples: $12-15 USD/sample
For 25-64 samples: $8-10 USD/sample
For 65-96 samples: $6-8 USD/sample
For 97+ samples: $5 USD/sample
In addition to the primer synthesis cost, amplification costs are $12-15 USD/sample.
If the primer includes U or I base, please contact the APM team for a price evaluation.
Please note, the resulting customized amplicon must be within a size range of 200-470bp.
Product sizeCan mix with Novogene’ssamples?Product to quote in SFDCThe process required in SFDCRemark200-470bpYesRSMD00203 Amplicon Metagenomics Sequencing (WOBI);RSMD00213 Amplicon Metagenomics Sequencing (WBI)Customized primer synthesis; PCR amplification;Amplicon library preparation; Sequencing (xx K tags);Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;Data releaseSame with normal amplicon sequencingYes, but customer does not want to pool with Novogene’s samples.RSMD00203 Amplicon Metagenomics Sequencing (WOBI);RSMD00213 Amplicon Metagenomics Sequencing (WBI)Customized primer synthesis; PCR amplification;Amplicon library preparation; Sequencing (xx K tags)Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;Data releaseSame with normal amplicon sequencing.Each library must have around 40 samples/library.Inquiry needed.Product sizeCan mix with Novogene’ssamples?Product to quote in SFDCThe process required in SFDCRemark200-470bpYesRSMD00203 Amplicon Metagenomics Sequencing (WOBI);RSMD00213 Amplicon Metagenomics Sequencing (WBI)Customized primer synthesis; PCR amplification;Amplicon library preparation; Sequencing (xx K tags);Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;Data releaseSame with normal amplicon sequencingYes, but customer does not want to pool with Novogene’s samples.RSMD00203 Amplicon Metagenomics Sequencing (WOBI);RSMD00213 Amplicon Metagenomics Sequencing (WBI)Customized primer synthesis; PCR amplification;Amplicon library preparation; Sequencing (xx K tags)Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;Data releaseSame with normal amplicon sequencing.Each library must have around 40 samples/library.Inquiry needed.If the client wants customized primer synthesis, how to quote? A: Quotation of service is based on the target amplicon size.
Product size
- Can mix with Novogene’s
samples?
Product to quote in SFDC
The process required in SFDC
Remark
200-470bp
Yes
RSMD00203 Amplicon Metagenomics Sequencing (WOBI);
RSMD00213 Amplicon Metagenomics Sequencing (WBI)
Customized primer synthesis; PCR amplification;
Amplicon library preparation; Sequencing (xx K tags);
Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;
Data release
Same with normal amplicon sequencing
Yes, but customer does not want to pool with Novogene’s samples.
RSMD00203 Amplicon Metagenomics Sequencing (WOBI);
RSMD00213 Amplicon Metagenomics Sequencing (WBI)
Customized primer synthesis; PCR amplification;
Amplicon library preparation; Sequencing (xx K tags)
Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;
Data release
Same with normal amplicon sequencing.
Each library must have around 40 samples/library.
Inquiry needed.
Product size
- Can mix with Novogene’s
samples?
Product to quote in SFDC
The process required in SFDC
Remark
200-470bp
Yes
RSMD00203 Amplicon Metagenomics Sequencing (WOBI);
RSMD00213 Amplicon Metagenomics Sequencing (WBI)
Customized primer synthesis; PCR amplification;
Amplicon library preparation; Sequencing (xx K tags);
Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;
Data release
Same with normal amplicon sequencing
Yes, but customer does not want to pool with Novogene’s samples.
RSMD00203 Amplicon Metagenomics Sequencing (WOBI);
RSMD00213 Amplicon Metagenomics Sequencing (WBI)
Customized primer synthesis; PCR amplification;
Amplicon library preparation; Sequencing (xx K tags)
Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;
Data release
Same with normal amplicon sequencing.
Each library must have around 40 samples/library.
Inquiry needed.
< 200bp and > 100bp
No
RSMD00803 PCR product Amplicon Metagenomics Sequencing (WOBI); RSMD00813 PCR product Amplicon Metagenomics Sequencing (WBI)
Customized primer synthesis; PCR amplification;
PCR free library preparation for PCR product; NovaSeq PE250 (M reads per library)/ Novaseq PE150(xx Gb per library);
Data QC/ Standard analysis (Means QIIME 1)/ Standard Analysis-QIIME 2;
Data release
Need client’s samples to pool into PCR library (One library can mix about 1-40 samples), only accept M reads or GB data for single library, but no promise data output for each sample.
> 470bp
No
Cannot provide this service
Please refer to FAQ 5.
- What is the conversion between tags and reads?
- A: There is no direct conversion between tags and reads. However, based on our experience, we provide the following approximate relationship:
50k tags correspond to approximately 0.2M reads; 100k tags correspond to approximately 0.4M reads; 200k tags correspond to approximately 0.8M reads; 400k tags correspond to approximately 1.6M reads.
Please note that the minimum data output we currently offer is 50k raw tags.
Why have we updated the sequencing parameter from PE250 to PE256?
- A: We have incorporated phased nucleotides into our standard amplification primers and barcodes to enhance the complexity of low-diversity libraries, which are typical in amplicon sequencing. While adding PhiX helps address low diversity, we found that phased primers
significantly improve sequencing quality and reduce the need for PhiX, leading to better overall data outcomes. For more information, please refer to the technical note on phased primers and its corresponding biweekly training.
Will we continue to offer the PE250 sequencing parameter going forward?
- A: No, we will no longer offer the PE250 sequencing parameter. The default sequencing parameter has been updated to PE256 across all products. For amplicon sequencing specifically, PE256 will be the standard for both standard and customized primers, as well as PCR products. Additionally, for amplicon sequencing and amplicon-based PCR products, the data output will also be provided in PE256 format.
What type of data will be provided for amplicon sequencing using the PE256 sequencing parameter? A: For standard primers (WBI/WOBI): We will provide the following data:
Raw demultiplexed reads with and without the phased nucleotides (0+0, 8+8), barcodes, and primers.
A list of barcodes, phased nucleotides, and primers.
Merged Reads (Raw Tags)
Clean Tags (with no chimera)
For customized primers (WBI/WOBI): We will provide the following data:
Raw demultiplexed reads with and without the barcodes and primers.
Merged Reads (Raw Tags)
Clean Tags (with no chimera)
- Note: Customized primers do not contain any phased nucleotides.
What are phased primers and phased nucleotides?
- A: Phased primers are specifically designed primers used in amplicon sequencing, where a few random nucleotides are added to the 5’ end of the primers. These random bases introduce variation in the starting positions of sequencing reads, helping to reduce sequencing artifacts and improve overall data quality. Phased nucleotides are positioned between the amplification primer and the barcodes. By randomizing nucleotides on both ends of the amplicon, library complexity is enhanced, leading to improved sequencing performance and data quality.
- How will phased nucleotides impact reads merging for amplicon sequencing?
- A: Phased nucleotides will not impact the average length of the amplicon in comparison to our previous pipeline. Our data handling method has also remained the same, but the only impact these phased nucleotides are on the length of sequences within the overlap region during reads merging between different samples. Overall, the overlap cutoff for reads merging is still set to ≥ 10bp and the shortest and longest overlap region within the sequences still meet this requirement.
What if the customer requires us to provide PE250 data for amplicon sequencing?
- A: We can provide this service for the customer but will require this information to be provided to the project managers ahead of time. For in the case of standard primers, we will trim the phased nucleotides and from the end of the fragment to meet the PE250 requirement. For customized primers, we will trim the additional 6 bp of reads at the end of the read since customized primers do not include any phased
nucleotides. There is no additional charge for this service but prior notice to the project managers is required.
What are the standard databases used for 16S, 18S, ITS amplicon analysis?
- A: The standard databases: 16S and 18S use Silva138 database; while ITS uses Unite V8.2 database.
Types
Databases
Description
Sample Types
Standard Databases
Silva
Bacteria and Archaea
16S region only
Silva
Eukaryotes (Fungi and Protists)
18S region only
Unite
Fungi
ITS region
What are the customized databases that we can offer and corresponding sample type?
TypeDatabasesDescriptionSample Types (Region)Customized: additional 25 USD/sample and TATmicroNTcurated microbial database based onNT databaseAll Types (Microbial)NTlarge database that is not limited to microbes but will have a longer TATAll Types (Microbial, Plants, Animals)Maarjamfor mycorrhizal fungiEnvironmentalTypeDatabasesDescriptionSample Types (Region)Customized: additional 25 USD/sample and TATmicroNTcurated microbial database based onNT databaseAll Types (Microbial)NTlarge database that is not limited to microbes but will have a longer TATAll Types (Microbial, Plants, Animals)Maarjamfor mycorrhizal fungiEnvironmentalA: Novogene provides a variety of customized databases. Using a customized database incurs an additional cost of $25 USD/sample on top of the standard analysis fee. Turnaround times (TAT) may vary by database; for example, the NT database requires the longest TAT, adding an extra 3-4 working days due to its size.
Type
Databases
Description
Sample Types (Region)
Customized: additional 25 USD/sample and TAT
microNT
curated microbial database based on
NT database
All Types (Microbial)
NT
large database that is not limited to microbes but will have a longer TAT
All Types (Microbial, Plants, Animals)
Maarjam
for mycorrhizal fungi
Environmental
Type
Databases
Description
Sample Types (Region)
Customized: additional 25 USD/sample and TAT
microNT
curated microbial database based on
NT database
All Types (Microbial)
NT
large database that is not limited to microbes but will have a longer TAT
All Types (Microbial, Plants, Animals)
Maarjam
for mycorrhizal fungi
Environmental
PR2
Protists but also contain metazoan,
fungi, and plants
Environmental
MitoFish
Fish Mitochondria Database
Environmental (12S primarily)
eHOMD
bacteria (human oral and aerodigestive
tract)
Human Only (16S only)
Grenegenes2 (Qiime2 only)
homogenization between 16sRNA and
shotgun metagenomics for bacteria and archaea only
All Types (16S only)
COIns
COI region for insects (COI-5-P)
Environmental (CO1 only)
- What is the difference between OTU(Qiime1) and ASV(Qiime2)?
Amplicon Sequence Variants-ASV (Qiime2)Operational Taxonomic Units-OTUs (Qiime1)Compare sequencing similarity (~ 99%)Taxonomy annotation on exact sequences.Read quality has higher impact on downstream analysis.Readily compared between studies.Clustering at 97% similarityTaxonomy annotation on representative sequenceRead quality has lower impact on downstream analysisRe-analysis is required if new data is added.Amplicon Sequence Variants-ASV (Qiime2)Operational Taxonomic Units-OTUs (Qiime1)Compare sequencing similarity (~ 99%)Taxonomy annotation on exact sequences.Read quality has higher impact on downstream analysis.Readily compared between studies.Clustering at 97% similarityTaxonomy annotation on representative sequenceRead quality has lower impact on downstream analysisRe-analysis is required if new data is added.A: OTUs in Qiime1 address sequencing errors by clustering reads, which can compromise accuracy and require project-specific clustering parameters. These unique parameters make re-analysis and reproducibility challenging for OTU-based projects. In contrast, Qiime2 uses DADA2 to denoise sample sequences rather than clustering, allowing for precise inference of sequences, distinguishing differences as small as a single nucleotide. Each de-duplicated sequence generated through DADA2 noise reduction is called an ASV (Amplicon Sequence Variant). ASVs facilitate easier reproducibility and enable cross-project analyses, providing a more robust solution than OTUs for microbiome studies. https://web.novogene.com/5-key-features-of-Qiime2-for-microbiome-analysis
Amplicon Sequence Variants-ASV (Qiime2)
Operational Taxonomic Units-OTUs (Qiime1)
Compare sequencing similarity (~ 99%)
Taxonomy annotation on exact sequences.
Read quality has higher impact on downstream analysis.
Readily compared between studies.
Clustering at 97% similarity
Taxonomy annotation on representative sequence
Read quality has lower impact on downstream analysis
Re-analysis is required if new data is added.
Amplicon Sequence Variants-ASV (Qiime2)
Operational Taxonomic Units-OTUs (Qiime1)
Compare sequencing similarity (~ 99%)
Taxonomy annotation on exact sequences.
Read quality has higher impact on downstream analysis.
Readily compared between studies.
Clustering at 97% similarity
Taxonomy annotation on representative sequence
Read quality has lower impact on downstream analysis
Re-analysis is required if new data is added.
- Note:
For customers primarily interested in species-level analysis, 16S full-length amplicon sequencing and deep shotgun metagenomic sequencing are recommended, as species resolution is more limited in standard amplicon sequencing compared to these approaches.
- How should a customer choose between Qiime1 and Qiime2 for function prediction analysis using PICRUSt or PICRUSt2?
- A: Function prediction using PICRUSt or PICRUSt2 is included in the standard Qiime2 analysis package, while in Qiime1, it is considered an advanced analysis and incurs an additional charge. We strongly recommend Qiime2 for function prediction analysis. This recommendation also applies to other function prediction software, such as Tax4Fun.
- How to quote for Qiime1/Qiime2 standard analysis?
- A: If you require Qiime1 standard analysis, select "Standard Analysis" in the SFDC system.
If you require Qiime2 standard analysis, select "Standard Analysis-QIIME 2" in the SFDC system.
For customized analysis, select "Customize Analysis" as usual and complete the "Customized Analysis Note" in the SFDC system.
What analysis content was added or removed after the most recent update in 2023?
- A: In 2023, Qiime1 and Qiime2 analysis pipelines were integrated into a single pipeline capable of producing either Qiime1 or Qiime2 results. As part of this update, some analyses specific to Qiime1, such as the evolutionary tree and Krona, were removed. However, new features were added, including Simper analysis, additional function prediction software, and advanced analysis options (Function Prediction, Correlation Analysis, and Environmental Association Analysis) now available in our reports. The primary distinction between Qiime1 and Qiime2 analyses is the data type used (OTUs vs. ASVs), with Qiime2 also offering one round of function prediction as part of the standard analysis.
For further details, please refer to the Excel document “Qiime1 and Qiime2 Demo Reports + Analysis Pipeline Update.”
Which version of the analysis pipeline should we recommend for pre-existing customers with ongoing WBI projects or those wishing to compare current samples to prior WBI projects
- A: For pre-existing customers with ongoing, non-longitudinal projects or those needing to compare current samples with previous WBI projects, we recommend using the previous analysis pipeline to maintain data consistency. For customers engaged in longer-term projects, please coordinate with the Technical Support and Project Management teams to gradually transition from the previous pipeline to the current one.
Why is it important to recommend the previous analysis pipeline over the updated one for pre-existing customers with ongoing projects or those comparing current samples to previous projects?
- A: There are slight differences in data processing between the old and new analysis pipelines, which may affect analysis results. Selecting the appropriate pipeline is essential for maintaining data consistency for the customer. Please indicate in the quotation under “Description-Note” the use of the previous analysis pipeline. We recommend that the Technical Support and Project Management teams assist the customer with transitioning to the current pipeline over time.
Are the results comparable between the two versions of our analysis pipeline (old vs 2023 new update)?
- A: No, the results are not directly comparable. Therefore, if customers wish to conduct cross-comparisons with previous projects, we recommend continuing with the old analysis pipeline.
Why is it important to have a completed BI form that includes both standard and advanced analysis sections for the final analysis report?
- A: The final analysis report will only include the advanced analysis section if the customer submits a fully completed BI form covering both standard and advanced analysis sections from the beginning. If an additional BI form with advanced analysis requirements is submitted after the initial analysis is complete, the advanced analysis results will be provided as a data release rather than integrated into the final report.
Additionally, customers may qualify for a discount on advanced analysis if they communicate these needs to Sales or Technical Support prior to quotation. However, if advanced analysis is completed based on a BI form submitted after the quotation stage, the full price of the advanced analysis will apply.
- How should the "Advanced Analysis" and "Customized Analysis" sections be quoted with the discount in SFDC?
- A: List the advanced analyses under "Customized Analysis" and include clear details in the "Customized Analysis Note" for each requested analysis.
Why are there so many different options for advanced analysis: Environmental Association Analysis?
- A: Spearman, CCA/RDA, and dbRDA analyses are required if the customer intends to perform Mantel or VPA analyses. This creates a range of options tailored to different research needs.
Please quote the specific Environmental Association Analysis option the customer is interested in under "Customized Analysis" and include detailed information in the "Customized Analysis Note."
What if a customer requires more than one Function Prediction software?
- A: For Qiime1, the customer must order two instances of Advanced Analysis-Function Prediction, while for Qiime2, only one additional Advanced Analysis-Function Prediction is required. Please inform the Project Managers in advance so they can coordinate the additional
function prediction accordingly. Refer to the table below for details on the different function prediction software options.
Please quote the additional function prediction under "Customized Analysis" and include specific details in the "Customized Analysis Note."
Region
Database
Description
16S
PICRUSt
applicable to a wider range of samples, for most samples.
PICRUSt2
an updated version of PICRUSt for a wider range of applications
FAPROTAX
predicting biochemical cycling processes in environmental samples;
TAX4Fun
suitable for functional prediction of gut and soil samples, but not for prediction of specific environmental samples, because microorganisms in the gut are relatively well studied, so it is optimal
for prokaryotic functional prediction of gut samples.
BugBase
phenotypic prediction of bacteria, ≥3 samples are required.
ITS
FUNGuild
suitable for fungi (ITS)
- Can the results for multiple Advanced Analysis-Function Prediction options be included in the final analysis report if the customer submits a completed BI form with both standard and advanced analysis sections?
- A: Yes, please inform the project managers in advance so they can make the necessary arrangements. Be sure to quote the additional function prediction under "Customized Analysis" and include detailed information in the "Customized Analysis Note."
Amplicon Sequencing with PCR Products
We accept PCR products amplified with amplicon sequencing primers for amplicon sequencing. These primers are specifically designed for targeted regions relevant to metabarcoding. Please note that these amplification primers differ from those used in mWGS PCR products, and genotyping PCR products are not accepted for this service.
## Sample Requirements
Sample Type
PCR Product size*
Client’s requirements
Amount
Volume
Concentra tion
Purity (NanoDropTM/ Agarose Gel)
PCR Products
with pair-end barcodes
Around 200-470bp
Want to pool with Novogene amplicons
≥ 200 ng
≥ 20 μL
≥ 10 ng/μL
OD260/280 = 1.8-2.0,
No degradation, no contamination, no color
PCR Products with pair-end barcodes
Above 100bp, less than 470bp
Want to pool their own samples in the library. must
pool their PCR products themselves**
Pooled amplicons sample ≥ 1.5 μg
≥ 20 μL
≥ 60 ng/μL
OD260/280 = 1.8-2.0,
No degradation, no contamination, no color
PCR Products (No Barcodes)
Fragment size: 100-500bp
Each PCR product for 1 single PCR-free Library
≥ 1.5 μg
≥ 20 μL
≥ 60 ng/μL
OD260/280 = 1.8-2.0,
No degradation, no contamination, no color
- Note:
Please refer to FAQ 5-7 for more information on amplicon size.
** Please refer to FAQ 1 for more information on customer pooling and PCR products.
Sequencing Strategy and Turnaround Time
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 36 samples)
WOBI
WBI
NovaSeq 500 Cycles*
100k tags/sample
(Can pool with Novogene Amplicons)
26 working days
32 working days
NovaSeq 500 Cycles*
1M raw reads or above/library (don’t /can’t pool with Novogene’s Amplicons)
26 working days
32 working days
- Note:
The sequencing strategy for amplicon sequencing is now known officially as NovaSeq 500 Cycles. This includes the use of PE256 due to the recent update that replaces our previous PE250 sequencing strategy as PE256. Please refer to FAQ 12-16 more information
Analysis Contents
For samples that can be pooled with Novogene’s amplicons, we can provide standard analysis. Please refer to our Qiime1/Qiime2 amplicon sequencing documentation for details on the analysis content available. For PCR products that cannot be pooled with Novogene’s amplicons, an evaluation will be necessary. Please submit an inquiry to the APM team with detailed information on the customer’s PCR products, including product size, amplified region, and barcode details (or indicate if barcodes are absent).
- Note:
If the customer requests analysis for either PCR products that can and cannot be pooled with Novogene’s amplicons, a demultiplexing fee of $4 USD per individual PCR product will apply.
Demo for Data Release Structure:
WOBI:
WBI:
Same as that of Amplicon Sequencing Analysis Qiime1/Qiime2
## FAQ
- What is some information that you will need to clarify with a customer when accepting their PCR products.
- A: Please refer to the table below for clarification when working with new amplicon sequencing inquires with PCR products.
Sample Type
Any Adapter Sequences?
PE Barcodes fulfill Novogene’s Requirements?
PCR-
Product Size
Solutions
Price and Product Offers
Remarks
Products in SFDC
Metabarcoding PCR Product Starting Material
Yes
PCR products containing adapter sequences must be prepared as libraries by the customer before submission, as we cannot provide library preparation for this type of PCR product. These samples must be submitted as premade libraries.
No
Yes
Size within 200-
470bp
- Can pool samples with Novogene's amplicon projects
Pricing refers to Amplicon Metagenomics (ie.100K raw tags)
50K tags or above per sample
RSMD00203
Amplicon Metagenomics Sequencing (WOBI); RSMD00213
Amplicon Metagenomics
Sequencing (WBI)
Client pool samples into 1 pooled sample (1-40
samples/pool)
Pricing refers to Customized/PCR product Amplicon Metagenomics
Clients need to pool PCR products into 1 pooled sample by themselves.
Only accept M read data for a single library, but no promises on data output for each sample
RSMD00803 PCR
product Amplicon Metagenomics Sequencing (WOBI); RSMD00813 PCR
product Amplicon Metagenomics Sequencing (WBI)
No
Size not within 200-
470bp
Client pool samples into 1 pooled sample (1-40
samples/pool)
Pricing refers to Customized/PCR product Amplicon Metagenomics
Clients need to pool PCR products into 1 pooled sample by themselves.
Only accept M reads or Gb data for a single library, but no promises in data output for each sample.
RSMD00803 PCR
product Amplicon Metagenomics Sequencing (WOBI); RSMD00813 PCR
product Amplicon Metagenomics Sequencing (WBI)
Why can’t we provide library preparation for PCR products containing adapter sequences?
- A: Adapter sequences within PCR products can interfere with our library preparation and sequencing processes. Therefore, customers must complete library preparation independently and submit these samples as premade libraries.
In addition to information on adapter sequences, what details are required from the customer to determine if we can provide library preparation for their samples?
- A: The following information is required from the customer:
Whether the PCR product contains adapter sequences
Size of the PCR product
Intended purpose of the PCR product (metabarcoding or genotyping)
If the PCR products are pooled
Whether PCR products are barcoded, and if so, whether barcodes are present on both ends and fits our requirements
Whether demultiplexing is required
- Note: Genotyping PCR products are not accepted for amplicon metagenomic PCR services.
If demultiplexing is required but the barcode does not meet Novogene’s specifications, please consult with the APM team.
Why do we only accept metabarcoding PCR products for amplicon metagenomic sequencing?
- A: Our amplicon metagenomic sequencing pipeline is specifically designed for metabarcoding amplicons/PCR products and is not optimized for genotyping PCR products. A key difference is that for metabarcoding PCR products, reads are merged during demultiplexing, whereas reads for genotyping PCR products should remain unmerged. This also applies to oligonucleotides, as our pipeline is not configured to process them, and reads from oligonucleotides should also remain unmerged.
Why must PCR products be limited to 200-470bp if the customer wishes to pool them with Novogene’s amplicons?
- A: Novogene’s amplicons typically range from 200-470bp. If the customer’s PCR products fall outside this size range, we will not be able to pool their samples with Novogene’s amplicons.
What if the expected PCR product exceeds 470bp?
- A: We do not accept PCR products over 470bp, as this limits our ability to conduct PCR-free library preparation and leads to suboptimal results during the read-merging process.
What happens when the expected amplicon is below 200bp?
- A: If the amplicon is under 200bp, it must be sequenced on PE150. Please note that we cannot accept amplicons (PCR products) shorter than 100bp, as this length is too short and generates excessive adapter reads, leading to suboptimal sequencing data for the customer.
What barcode specifications are required if a customer wishes to pool their samples with Novogene’s samples?
- A: Both the forward and reverse barcodes must be 8bp in length, with no repeating sequences. The customer should provide PCR products that are dual-barcoded (forward and reverse) with unique, non-repetitive barcodes on each end. Please request the customer to supply the individual barcode sequences for each sample prior to library preparation.
- Can we accept 6bp barcodes?
- A: Yes, we can accept 6bp barcodes. However, the customer must provide the individual barcode sequences for both the forward and reverse sides of each sample prior to library preparation. Please confirm that both the forward and reverse primers are barcoded and unique.
What happens if the customer’s barcodes do not meet our requirements?
- A: If the customer’s barcodes do not meet our requirements (e.g., contain repeats or are one-sided), we will be unable to pool their PCR products with Novogene’s amplicons. In this case, the customer will need to pool their samples independently and send us the pooled samples for library preparation.
What if the PCR products lack barcodes?
- A: In this case, we will treat the samples as standard PCR products, with each PCR product used to create a separate PCR-free library. Please confirm that the samples are within the 100-500bp range and quote the appropriate sequencing platform. Be sure to note the PCR product insert size in the “Description-Note” section of the quotation.
Which sequencing parameter will we use for PCR products for amplicon metagenomic sequencing?
- A: We will use the PE256 sequencing parameter for all PCR products within the 200-470bp range and PE150 for PCR products within the 100-200bp range.
Why have we updated the sequencing parameter from PE250 to PE256?
- A: We have incorporated phased nucleotides into our standard amplification primers and barcodes to enhance the complexity of low-diversity libraries, which are typical in amplicon sequencing. While adding PhiX helps address low diversity, we found that phased primers significantly improve sequencing quality and reduce the need for PhiX, leading to better overall data outcomes. For more information, please refer to the technical note on phased primers and its corresponding biweekly training.
Will we continue to offer the PE250 sequencing parameter going forward?
- A: No, we will no longer offer the PE250 sequencing parameter. The default sequencing parameter has been updated to PE256 across all products. For amplicon sequencing specifically, PE256 will be the standard for both standard and customized primers, as well as PCR products. Additionally, for amplicon sequencing and amplicon-based PCR products, the data output will also be provided in PE256 format.
What type of data will be provided for PCR products for amplicon metagenomic sequencing using the PE256 sequencing parameter? A: For demultiplexed PCR products (WBI/WOBI): We will provide the following data:
Raw demultiplexed reads with and without the barcodes and primers.
Merged Reads (Raw Tags)
Clean Tags (with no chimera)
- Note:
Demultiplexing fees will apply for PCR products that require demultiplexing. Please refer to FAQ 17 for more information.
What if the customer requires us to provide PE250 data for PCR products for amplicon metagenomic sequencing?
- A: We can provide this service for the customer but will require this information to be provided to the project managers ahead of time. For customer’s PCR products, we will trim the additional 6 bp of reads at the end of the read.
There is no additional charge for this service but prior notice to the project managers is required.
- Can we provide demultiplexing for customer’s pooled and barcoded PCR products?
- A: It depends, and there is an additional fee of $4 USD per individual PCR product within each pooled sample, not per pooled sample. Please submit an inquiry to the APM team, including barcode information, sequencing primer details, and the number of PCR products in each pool. Ensure that the provided information is complete and concise, as it will directly impact the evaluation results.
- Can we provide demultiplexing for customer’s pooled but non-barcoded PCR products?
- A: No, we will only be able to demultiplex the customer’s samples via the samples’ barcodes and not via their amplification primers.
- Can we provide our standard analysis (Qiime1 or Qiime2) if requested by the customer?
- A: This depends on whether the customer’s PCR products can be pooled with Novogene’s amplicons. We can provide standard analysis for PCR products that can be pooled with Novogene’s amplicons. For PCR products that cannot be pooled, the suitability of standard analysis will depend on the product size, amplified region, and barcode configuration. In both cases, a demultiplexing fee of $4 USD per individual PCR product will apply. If a customized database is needed, an additional charge of $25 USD/PCR product will be added to the standard analysis cost.
What are the customized databases that we can offer and corresponding sample type?
TypeDatabasesDescriptionSample Types (Region)Customized: additional 25 USD/sample and TATmicroNTcurated microbial database based onNT databaseAll Types (Microbial)NTlarge database that is not limited to microbes but will have a longer TATAll Types (Microbial, Plants, Animals)Maarjamfor mycorrhizal fungiEnvironmentalPR2Protists but also contain metazoan,fungi, and plantsEnvironmentalMitoFishFish Mitochondria DatabaseEnvironmental (12S primarily)TypeDatabasesDescriptionSample Types (Region)Customized: additional 25 USD/sample and TATmicroNTcurated microbial database based onNT databaseAll Types (Microbial)NTlarge database that is not limited to microbes but will have a longer TATAll Types (Microbial, Plants, Animals)Maarjamfor mycorrhizal fungiEnvironmentalPR2Protists but also contain metazoan,fungi, and plantsEnvironmentalMitoFishFish Mitochondria DatabaseEnvironmental (12S primarily)A: Novogene provides a variety of customized databases. Using a customized database incurs an additional cost of $25 USD/sample on top of the standard analysis fee. Turnaround times (TAT) may vary by database; for example, the NT database requires the longest TAT, adding an extra 3-4 working days due to its size.
Type
Databases
Description
Sample Types (Region)
Customized: additional 25 USD/sample and TAT
microNT
curated microbial database based on
NT database
All Types (Microbial)
NT
large database that is not limited to microbes but will have a longer TAT
All Types (Microbial, Plants, Animals)
Maarjam
for mycorrhizal fungi
Environmental
PR2
Protists but also contain metazoan,
fungi, and plants
Environmental
MitoFish
Fish Mitochondria Database
Environmental (12S primarily)
Type
Databases
Description
Sample Types (Region)
Customized: additional 25 USD/sample and TAT
microNT
curated microbial database based on
NT database
All Types (Microbial)
NT
large database that is not limited to microbes but will have a longer TAT
All Types (Microbial, Plants, Animals)
Maarjam
for mycorrhizal fungi
Environmental
PR2
Protists but also contain metazoan,
fungi, and plants
Environmental
MitoFish
Fish Mitochondria Database
Environmental (12S primarily)
eHOMD
bacteria (human oral and aerodigestive
tract)
Human Only (16S only)
Grenegenes2 (Qiime2 only)
homogenization between 16sRNA and
shotgun metagenomics for bacteria and archaea only
All Types (16S only)
COIns
COI region for insects (COI-5-P)
Environmental (CO1 only)
PacBio Full-Length 16S Sequencing
## Sample Requirements
Library Type
Sample Type
Amount
Concentration
Purity (NanoDropTM / Agarose Gel)
Kinnex full-length 16S library
Genomic DNA
≥ 300 ng*
≥ 10 ng/μL
Clear main band; No degradation; No contamination
- Note:
Clients must provide samples meeting our minimum specifications. For samples requiring DNA extraction, additional input material and/or repeated extraction may be necessary to obtain sufficient DNA quantity, depending on sample type and quality.
Sequencing Strategy and Turnaround Time
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 36 samples) *
WOBI
WBI
Revio SPRQ-Kinnex
20K HiFi/CCS reads or above
30 working days
40 working days
- Note:
TAT will be longer than expected if “Pass” samples did not meet the data requirement after one round of sequencing and will require top-up sequencing.
Analysis Contents
Standard Analysis - Full-length 16S Sequencing
Software
Primer excision, chimera filtration, denoise-ASVs
QIIME2
Taxonomic analysis:
Taxonomy annotation, Bar plots at different taxonomic level
QIIME2
Alpha Diversity Analysis:
Alpha diversity index, Alpha rarefaction, Alpha group significance
QIIME2
Beta Diversity:
Beta diversity metric, Beta group significance, Principal coordinates analysis
QIIME2
Statistics and Plottings:
Differential abundance on sequence level, Differential abundance on taxonomic level, Venn analysis, Metastats, LEfSe
QIIME2, R, Metastats, LEfSe
Data delivery
WOBI project: fastq will be delivered as default.
WBI project: fastq and analysis result will be delivered as default.
## FAQ
- Can we perform DNA extraction if the client wants to order full-length 16S sequencing?
- A: Yes, we provide DNA extraction for full-length 16S sequencing when the sample type is within our supported range. While the extraction protocol is identical for both standard (NovaSeq) and full-length (PacBio) amplicon sequencing, they differ in primer selection for amplification.
- Note:
Some sample types may require additional input material or repeated extraction to yield sufficient DNA. Additional extraction procedures will incur extra charges.
For detailed extraction requirements, please consult our amplicon sequencing documentation
If a client sends us PCR product with PacBio’s barcode, can we accept this kind of samples?
- A: Yes, we can process pre-barcoded PCR products for PacBio sequencing, provided they meet our requirements. The minimum input is >2 μg of linear PCR product, ideally within the 15–18 kb range; fragments shorter than 1 kb cannot be accepted. Clients may pool barcoded samples, but we highly recommend using PacBio’s official barcodes and limiting each Cell to <100 PCR products of similar size to ensure optimal data distribution. Please note that we deliver whole Cell data without demultiplexing and do not guarantee specific data output per sample or Cell.
- How many samples can sequence in 1 SMRT Cell?
- A: For gDNA samples, our full-length 16S service (including amplification, library prep, and sequencing) typically supports 250–300 samples per Revio Cell, assuming ~10K CCS reads per sample. For prepared PCR products, we sell sequencing by the full Cell, and clients may pool samples themselves (refer to FAQ 2 for pooling guidelines).
- Can we offer full-length 18S or ITS sequencing?
- A: We currently do not provide full-length 18S or ITS sequencing as a standard service. However, for large-scale projects (>100 samples), please reach to the APM team for a case-by-case evaluation.
TargetAmplicon SizePrimer namePrimer sequence (5’-3’)16S rRNA gene~ 1500 bp27FAGRGTTYGATYMTGGCTCAG1492RGYTACCTTGTTACGACTTTargetAmplicon SizePrimer namePrimer sequence (5’-3’)16S rRNA gene~ 1500 bp27FAGRGTTYGATYMTGGCTCAG1492RGYTACCTTGTTACGACTTCould you please clarify which primer set is used for full-length 16S sequencing and indicate the fragment length? A:
Target
Amplicon Size
Primer name
Primer sequence (5’-3’)
16S rRNA gene
~ 1500 bp
27F
AGRGTTYGATYMTGGCTCAG
1492R
GYTACCTTGTTACGACTT
Target
Amplicon Size
Primer name
Primer sequence (5’-3’)
16S rRNA gene
~ 1500 bp
27F
AGRGTTYGATYMTGGCTCAG
1492R
GYTACCTTGTTACGACTT
Novogene Product Manual
Microbial WGS Sequencing
AMEA 2023.09
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director. If you have any questions about the products, please consult the APM team.)
Product Manual Revisions
Subject
Novogene Product Manual-8 Microbial WGS Product Manual-2023 H2 V1.0
Revision Number
2023 V1.0
Issue Date
Sept 12th, 2023
Prepared by
Chen Yu
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Separated mWGS from the initial product manual. Included new Biosafety regulations
Updated mWGS and mWGS PCR Products Included Bacteria Draft Map and Fungal Survey
Chen Yu
Sept 11th, 2023
Contents
Biosafety Regulations: Singapore5
Biosafety Levels and Schedules Introduction5
First and Second Schedule6
Third to Fifth Schedules7
Biosafety Regulations: China8
Novogene’s Requirements for Infectious Microbes8
Species Summary Comparison Chart9
Species Comparison Chart9
Microbial Genome Resequencing10
DNA extraction10
## Sample Requirements11
Sequencing Strategy and Turnaround Time11
Analysis Contents11
Demo for Data Release Structure12
## FAQ14
Microbial PCR Product20
## Sample Requirements20
Sequencing Strategy and Turnaround Time20
Analysis Contents21
Demo for Data Release Structure21
## FAQ22
Bacteria Draft Map24
DNA extraction24
## Sample Requirements24
Sequencing Strategy and Turnaround Time25
Analysis Contents25
Demo for Data Release Structure27
## FAQ28
Fungal Survey30
## Sample Requirements30
Sequencing Strategy and Turnaround Time30
Demo for Data Release Structure31
## FAQ31
Biosafety Regulations: Singapore
Any microbes entering the labs in Singapore (SG lab and CSA lab) must follow the biosafety regulations set up by Singapore's Ministry of Health (MOH) and in some cases, Singapore's Animal Veterinarian Society (AVS) as well. Both of our Singapore Labs (SG lab and CSA lab) are BSL-2 (Biological Safety Level-2). Please see below for more information on the biosafety regulations.
Biosafety Levels and Schedules Introduction
The Biological Agents and Toxins Act (BATA) organizes various microbes into 5 Schedules. Depending on the risk of the biological agents/toxins, different levels of controls are adopted and enforced for each Schedule. Please see the pdf, “Singapore-list of biological agents and toxins”, in the shared wedrive under “Product related support documents” in the APM folder for more information.
First and Second Schedule
Microorganisms listed under First Schedule (Part I and Part II) and Second Schedule are heavily regulated by the MOH and AVS. Some of these microogranisms will require MOH’s approval and special permit to possess and to work with these microorganisms. The reason for this is because many of these microoganisms are in highly infectious and will require special facilities to work with them safely. Many of these microorganisms are classified as BSL-3 and BSL-4. Since both the SG and CSA labs are BSL-2 labs, they lack the facilities and the certification on take on these active microorganisms.
For inactivated biological agents (gDNA and PML) from the First and Second Schedule, the SG lab will only be able to accept these samples if the following steps are followed:
Customer MUST submit a “Proof of Inactivation” to the MOH for an evaluation.
Customer MUST receive an “Import permit” from MOH.
Customer provides us a copy of the inactivation proofs and import permit.
TS/PM MUST provide an advance notice to the logistics team and SG lab prior to sample collection and sample arrival.
- Note: Please note that this applies to customers within and outside of Singapore. The “import” here means the transfer from one facility to another nationally and internationally. Failure to comply or negligence within this area may result in:
Causing a biosafety hazard for lab colleagues within SG lab
Violation against Singapore’s Biological Agents and Toxins Act 2005
Be liable to any conviction or fines handed out by Singapore’s government.
Be liable to any consequences outlined by Novogene.
For more information regarding the various requirements, please visit this website: https://www.moh.gov.sg/biosafety/faqs
Third to Fifth Schedules
Given that both SG and CSA labs are BSL-2 labs, they will be able to receive and work with microbes listed under the Third Schedule, Fourth Schedule, and Fifth Schedule. Please note that this corresponds to BSL-1 and some BSL-2 microbes.
Both labs will be able to work with the gDNA of the microbes listed under the Third to Fifth Schedule. However, prior to sample collection please confirm with the customer that the microbes entering the labs have been deactivated and the tubes have been decontaminated. Please also provide a heads-up to the logistics team and the corresponding laboratory for any incoming samples from infectious microbes so that the lab can make the necessary preparations beforehand.
Biosafety Regulations: China
Any microbes entering the labs in China (Beijing and Tianjin Labs) must follow the biosafety regulations set up by National Health Commission of the People’s Republic of China and the internal regulations required by Novogene. The National Health Commission of the People’s Republic of China have provided an extensive directory of pathogenic microorganisms, “ 人间传染的病原微生物目录”, or translated as “Directory of Human Pathogenic Microorganisms”, where various microorganisms and their biosafety levels are classified. Please refer to this document within the shared wedrive under the APM’s folder: “Product related support documents”.
Novogene’s Requirements for Infectious Microbes
Raw samples and gDNA from any microorganisms that that appear within the “Directory of Human Pathogenic Microorganisms” are not accepted by Novogene even if the customer may have inactivated the samples. This includes any samples that are associated with these microbes, such as bacteriophages, or microorganisms that may not necessarily appear within the list but have a history of opportunistic infection of humans. The main reason is because both the Beijing lab and the Tianjin labs are not equipped to handle these types of samples.
If the customer would like to send us the samples as premade libraries, please verify with the customer on their microbial information. Premade libraries made from microbes can only but extreme caution is advisory when sending any of these samples to the labs in China. Please confirm with the customer that the tubes and the packaging containing their samples have been thoroughly decontaminated.
Species Summary Comparison Chart
Species Comparison Chart
- Note:
* Must confirm the sample’s lab destination and biosafety regulations prior to accepting any microbial samples!
** Our DNA extraction form bacteria solution and cell pellet are limited to Gram-negative bacteria. For more information, please refer to FAQ 3
*** Our DNA extraction for yeast is limited to yeast and no other fungi. For more information, please refer to FAQ 4.
Microbial Genome Resequencing
Bacterial and fungal whole-genome re-sequencing is a critical tool for understanding the variation information between different strains or new organisms. Microbial genome resequencing is a method of mutation detection based on high-throughput sequencing data of microbial libraries and comparison with the reference genome. SNP, InDel, SV, and CNV variation information of strain and reference genome were detected.
DNA extraction
Sample types*
Species
Recommended Input
Replicates
Tube Recommendations
Transportations
Bacterial solution (log phase)
Bacteria**
≥ 4ml
2
Sterile, Pre-cooled
1.5/2.0ml EP Tube
Dry Ice
Bacterial cell pellet
Bacteria**
Centrifugation of corresponding bacterial solution
2
Sterile, Pre-cooled
1.5/2.0ml EP Tube
Dry Ice
Yeast cells (e.g., Saccharomyces, Candida, Pichia)
Yeast***
Pellet the yeast cells from a saturated 1.5ml culture (approx. 8-10 A600 unites for each ml) by centrifugation in a microcentrifuge at >- 10,000 rpm for 2-5 minutes
3
1.5ml Eppendorf tube
Dry Ice
Yeast Colonies
from Solid Medium
Yeast***
Scrape a single yeast colony (2 mm in diameter) from an agar plate or similar medium
3
1.5ml Eppendorf tube
Dry Ice
- Note:
Must confirm the sample’s lab destination and biosafety regulations prior to accepting any microbial samples!
* Please check with the APM team on kit availability for any projects that will need DNA extraction in CSA lab. For more details, please refer to the Sample Extraction Service in the price list.
** Our DNA extraction from bacteria solution and cell pellet are limited to Gram-negative bacteria. For more information, please refer to FAQ 3.
*** Our DNA extraction for yeast is limited to yeast and no other fungi. For more information, please refer to FAQ 4.
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity (Qubit/agarose gel)
Microbial whole genome library*
Genomic DNA
≥ 200 ng
≥ 20 μL
≥ 10 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination, no color
Microbial whole genome library
(PCR-free 350bp library)
Genomic DNA
≥ 1.2 μg
≥ 20 μL
≥ 50 ng/μL
- Note:
Please refer to FAQ.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 30 samples)
WOBI
WBI
Microbial whole genome library
NovaSeq PE150
100× (bacteria) 100× or above (fungus)*
at least 1Gb data per library
15 working days
23 working days
Analysis Contents
Standard Analysis-Bacterial/ fungal
Software
Data quality control: filtering reads containing adapters or low-quality reads
Fastp
Alignment with reference
BWA, Sambamba, Samtools
SNP/InDel calling, annotation and statistics
GATK, ANNOVAR
SV calling, annotation and statistics
BreakDancer, ANNOVAR
CNV calling, annotation and statistics
Cnvnator, ANNOVAR
Variation Map of Whole Genome
Circos
Demo for Data Release Structure
WOBI
WBI
## FAQ
*Please refer to the biosafety regulations for the various labs when talking with to the customer about any potential projects.
Biosafety Related Due Diligence NeededRequirements:1. Know which lab will be handling these samples if this project comes in.1.1 China-bound: please refer to the biosafety regulations of China and Novogene.1.2 Singapore-bound: please refer to the biosafety regulations set by the MOH.2. Check whether or not the microbes appear on the infectious/pathogenic list for theircorresponding country.2.1 China-bound: Please refer to “China-Human Pathogenic Microorganisms Directory”.2.2 Singapore-bound: Please refer to “Singapore-List of Biological Agents and Toxins”.3. If samples appear on the lists, check the BSL-levels/classification of the microbes.3.1 Singapore: Please refer to the various Schedules as designated by the MOH.Handling of samples will differ depending on the schedules and whether or not the samples have been deactivated.3.2 China: does not accept any samples that appear on the list. Nor do the labs acceptany microbes that have a history of opportunistic human infection.4. (Singapore-bound)Check whether or not these samples have been deactivated and decontaminated.If yes, please refer to the requirements on the right. If samples are not deactivated, please refer to the table below.If deactivated samples are from Schedule 1 and 2, customer must contact the MOH for an inactivation evaluation and for an import permit. Once received, the customer should provide us a copy of their documentations. TS/PM must provide an advance notice to the lab.If deactivated samples are from Schedule 3-5, the lab will be able to accept these samples. However, please provide an advance notice to the lab prior to samplecollection.5. (Singapore-bound) non-deactivated samples5.1.1 Schedule 1-2: Cannot accept non-deactivated samples.5.1.2. Schedule 3-5: This can only be accepted on a case-by-case situation.Biosafety Related Due Diligence NeededRequirements:1. Know which lab will be handling these samples if this project comes in.1.1 China-bound: please refer to the biosafety regulations of China and Novogene.1.2 Singapore-bound: please refer to the biosafety regulations set by the MOH.2. Check whether or not the microbes appear on the infectious/pathogenic list for theircorresponding country.2.1 China-bound: Please refer to “China-Human Pathogenic Microorganisms Directory”.2.2 Singapore-bound: Please refer to “Singapore-List of Biological Agents and Toxins”.3. If samples appear on the lists, check the BSL-levels/classification of the microbes.3.1 Singapore: Please refer to the various Schedules as designated by the MOH.Handling of samples will differ depending on the schedules and whether or not the samples have been deactivated.3.2 China: does not accept any samples that appear on the list. Nor do the labs acceptany microbes that have a history of opportunistic human infection.4. (Singapore-bound)Check whether or not these samples have been deactivated and decontaminated.If yes, please refer to the requirements on the right. If samples are not deactivated, please refer to the table below.If deactivated samples are from Schedule 1 and 2, customer must contact the MOH for an inactivation evaluation and for an import permit. Once received, the customer should provide us a copy of their documentations. TS/PM must provide an advance notice to the lab.If deactivated samples are from Schedule 3-5, the lab will be able to accept these samples. However, please provide an advance notice to the lab prior to samplecollection.5. (Singapore-bound) non-deactivated samples5.1.1 Schedule 1-2: Cannot accept non-deactivated samples.5.1.2. Schedule 3-5: This can only be accepted on a case-by-case situation.What are the biosafety related due diligence that you must perform when talking with the customer about their samples? A: Please refer to the table below for the biosafety related due diligence that must be done:
Biosafety Related Due Diligence Needed
Requirements:
1. Know which lab will be handling these samples if this project comes in.
1.1 China-bound: please refer to the biosafety regulations of China and Novogene.
1.2 Singapore-bound: please refer to the biosafety regulations set by the MOH.
2. Check whether or not the microbes appear on the infectious/pathogenic list for their
corresponding country.
2.1 China-bound: Please refer to “China-Human Pathogenic Microorganisms Directory”.
2.2 Singapore-bound: Please refer to “Singapore-List of Biological Agents and Toxins”.
3. If samples appear on the lists, check the BSL-levels/classification of the microbes.
3.1 Singapore: Please refer to the various Schedules as designated by the MOH.
Handling of samples will differ depending on the schedules and whether or not the samples have been deactivated.
3.2 China: does not accept any samples that appear on the list. Nor do the labs accept
any microbes that have a history of opportunistic human infection.
4. (Singapore-bound)
Check whether or not these samples have been deactivated and decontaminated.
If yes, please refer to the requirements on the right. If samples are not deactivated, please refer to the table below.
If deactivated samples are from Schedule 1 and 2, customer must contact the MOH for an inactivation evaluation and for an import permit. Once received, the customer should provide us a copy of their documentations. TS/PM must provide an advance notice to the lab.
If deactivated samples are from Schedule 3-5, the lab will be able to accept these samples. However, please provide an advance notice to the lab prior to sample
collection.
5. (Singapore-bound) non-deactivated samples
5.1.1 Schedule 1-2: Cannot accept non-deactivated samples.
5.1.2. Schedule 3-5: This can only be accepted on a case-by-case situation.
Biosafety Related Due Diligence Needed
Requirements:
1. Know which lab will be handling these samples if this project comes in.
1.1 China-bound: please refer to the biosafety regulations of China and Novogene.
1.2 Singapore-bound: please refer to the biosafety regulations set by the MOH.
2. Check whether or not the microbes appear on the infectious/pathogenic list for their
corresponding country.
2.1 China-bound: Please refer to “China-Human Pathogenic Microorganisms Directory”.
2.2 Singapore-bound: Please refer to “Singapore-List of Biological Agents and Toxins”.
3. If samples appear on the lists, check the BSL-levels/classification of the microbes.
3.1 Singapore: Please refer to the various Schedules as designated by the MOH.
Handling of samples will differ depending on the schedules and whether or not the samples have been deactivated.
3.2 China: does not accept any samples that appear on the list. Nor do the labs accept
any microbes that have a history of opportunistic human infection.
4. (Singapore-bound)
Check whether or not these samples have been deactivated and decontaminated.
If yes, please refer to the requirements on the right. If samples are not deactivated, please refer to the table below.
If deactivated samples are from Schedule 1 and 2, customer must contact the MOH for an inactivation evaluation and for an import permit. Once received, the customer should provide us a copy of their documentations. TS/PM must provide an advance notice to the lab.
If deactivated samples are from Schedule 3-5, the lab will be able to accept these samples. However, please provide an advance notice to the lab prior to sample
collection.
5. (Singapore-bound) non-deactivated samples
5.1.1 Schedule 1-2: Cannot accept non-deactivated samples.
5.1.2. Schedule 3-5: This can only be accepted on a case-by-case situation.
QuestionTypesQuestions to Askthe CustomerFollow-up ClarificationQuestionsPossible SolutionsBiosafety Related QuestionsQ1. What kind of species are the customer working with?Q1.1 Do the samples meet the biosafety regulations set by the in-bound country?Yes, to Q2; No to A1.1.A1.1 Please refer to the biosafety regulations mentioned above and FAQ1 for more information.Sample Related QuestionQ2. What kind of species are they working with?Q2.1 Do the samples fall under microorganisms? Yes, to A2.1; No to A2.2.A2.1 Need to confirm with the customer if their samples are bacteria of fungi. For any other microbes such as viruses, protists and algae, please submit an inquiry to the APM team.A2.2 For organisms that may fall in between PAWGS and mWGS due to their small size (ie.Helminths), please submit an inquiry to the APMteam for an evaluation.Q3. Do they need DNA extraction? Yes, to Q3.1; No to Q4.Q3.1 Are the samples on the DNA extraction list? Yes, to Q3.2; No, to A3.1 Q3.2 Have they done any pretreatment to their samples? Yes, to A3.2; No,to A3.3.A3.1 Please submit an inquiry to the APM for an evaluation for DNA extraction service.A3.2 Please submit an inquiry with details on the pretreatment done to the samples.A3.3 Please proceed with our standard sample requirements.Analysis-based QuestionsQ4. Do they have a reference genome for their samples? Yes, to Q4.1; No, toA4.3Q4.1 Can they provide us with fasta file and gff/gtf file for the reference genome? Yes, to A4.1; No, to A4.2.A4.1 Proceed with standard analysis.A4.2 Depending on the file type, we may be able to provide variant calling but cannot provide variant annotation.A4.3 Please proceed with either draft map, fungal survey or bacteriacomplete map/fungi fine map for this customer.QuestionTypesQuestions to Askthe CustomerFollow-up ClarificationQuestionsPossible SolutionsBiosafety Related QuestionsQ1. What kind of species are the customer working with?Q1.1 Do the samples meet the biosafety regulations set by the in-bound country?Yes, to Q2; No to A1.1.A1.1 Please refer to the biosafety regulations mentioned above and FAQ1 for more information.Sample Related QuestionQ2. What kind of species are they working with?Q2.1 Do the samples fall under microorganisms? Yes, to A2.1; No to A2.2.A2.1 Need to confirm with the customer if their samples are bacteria of fungi. For any other microbes such as viruses, protists and algae, please submit an inquiry to the APM team.A2.2 For organisms that may fall in between PAWGS and mWGS due to their small size (ie.Helminths), please submit an inquiry to the APMteam for an evaluation.Q3. Do they need DNA extraction? Yes, to Q3.1; No to Q4.Q3.1 Are the samples on the DNA extraction list? Yes, to Q3.2; No, to A3.1 Q3.2 Have they done any pretreatment to their samples? Yes, to A3.2; No,to A3.3.A3.1 Please submit an inquiry to the APM for an evaluation for DNA extraction service.A3.2 Please submit an inquiry with details on the pretreatment done to the samples.A3.3 Please proceed with our standard sample requirements.Analysis-based QuestionsQ4. Do they have a reference genome for their samples? Yes, to Q4.1; No, toA4.3Q4.1 Can they provide us with fasta file and gff/gtf file for the reference genome? Yes, to A4.1; No, to A4.2.A4.1 Proceed with standard analysis.A4.2 Depending on the file type, we may be able to provide variant calling but cannot provide variant annotation.A4.3 Please proceed with either draft map, fungal survey or bacteriacomplete map/fungi fine map for this customer.What are some of the questions that you ask when a customer is interested in microbial WGS inquiries? A: Please refer to the table below for example questions for customers with new microbial WGS inquiries.
Question
Types
Questions to Ask
the Customer
Follow-up Clarification
Questions
Possible Solutions
Biosafety Related Questions
Q1. What kind of species are the customer working with?
Q1.1 Do the samples meet the biosafety regulations set by the in-bound country?
Yes, to Q2; No to A1.1.
A1.1 Please refer to the biosafety regulations mentioned above and FAQ1 for more information.
Sample Related Question
Q2. What kind of species are they working with?
Q2.1 Do the samples fall under microorganisms? Yes, to A2.1; No to A2.2.
A2.1 Need to confirm with the customer if their samples are bacteria of fungi. For any other microbes such as viruses, protists and algae, please submit an inquiry to the APM team.
A2.2 For organisms that may fall in between PAWGS and mWGS due to their small size (ie.Helminths), please submit an inquiry to the APM
team for an evaluation.
Q3. Do they need DNA extraction? Yes, to Q3.1; No to Q4.
Q3.1 Are the samples on the DNA extraction list? Yes, to Q3.2; No, to A3.1 Q3.2 Have they done any pretreatment to their samples? Yes, to A3.2; No,
to A3.3.
A3.1 Please submit an inquiry to the APM for an evaluation for DNA extraction service.
A3.2 Please submit an inquiry with details on the pretreatment done to the samples.
A3.3 Please proceed with our standard sample requirements.
Analysis-based Questions
Q4. Do they have a reference genome for their samples? Yes, to Q4.1; No, to
A4.3
Q4.1 Can they provide us with fasta file and gff/gtf file for the reference genome? Yes, to A4.1; No, to A4.2.
A4.1 Proceed with standard analysis.
A4.2 Depending on the file type, we may be able to provide variant calling but cannot provide variant annotation.
A4.3 Please proceed with either draft map, fungal survey or bacteria
complete map/fungi fine map for this customer.
Question
Types
Questions to Ask
the Customer
Follow-up Clarification
Questions
Possible Solutions
Biosafety Related Questions
Q1. What kind of species are the customer working with?
Q1.1 Do the samples meet the biosafety regulations set by the in-bound country?
Yes, to Q2; No to A1.1.
A1.1 Please refer to the biosafety regulations mentioned above and FAQ1 for more information.
Sample Related Question
Q2. What kind of species are they working with?
Q2.1 Do the samples fall under microorganisms? Yes, to A2.1; No to A2.2.
A2.1 Need to confirm with the customer if their samples are bacteria of fungi. For any other microbes such as viruses, protists and algae, please submit an inquiry to the APM team.
A2.2 For organisms that may fall in between PAWGS and mWGS due to their small size (ie.Helminths), please submit an inquiry to the APM
team for an evaluation.
Q3. Do they need DNA extraction? Yes, to Q3.1; No to Q4.
Q3.1 Are the samples on the DNA extraction list? Yes, to Q3.2; No, to A3.1 Q3.2 Have they done any pretreatment to their samples? Yes, to A3.2; No,
to A3.3.
A3.1 Please submit an inquiry to the APM for an evaluation for DNA extraction service.
A3.2 Please submit an inquiry with details on the pretreatment done to the samples.
A3.3 Please proceed with our standard sample requirements.
Analysis-based Questions
Q4. Do they have a reference genome for their samples? Yes, to Q4.1; No, to
A4.3
Q4.1 Can they provide us with fasta file and gff/gtf file for the reference genome? Yes, to A4.1; No, to A4.2.
A4.1 Proceed with standard analysis.
A4.2 Depending on the file type, we may be able to provide variant calling but cannot provide variant annotation.
A4.3 Please proceed with either draft map, fungal survey or bacteria
complete map/fungi fine map for this customer.
Q5. Do the
customer need any
functional gene
A5.1 Functional gene annotation results can only be provided through
annotation results
bacteria draft map. The sequenced data can be used for bacteria draft
alongside their
map analysis as well. Please refer to FAQ 14 for more information.
variant analysis?
A5.2. Proceed with microbial resequencing standard analysis.
Yes to A5.1; N, to
A5.2
Why are our current DNA extraction solutions for bacteria solution and cell-pellet limited to Gram-negative bacteria?
- A: At the moment, both the SG lab and the CSA lab do not have the permit nor the necessary reagents needed for Gram-positive bacteria. If a customer is interested in doing DNA extraction from Gram-positive bacteria, please reach out to the APM team for an evaluation.
- Can we provide DNA extraction for other fungi samples other than yeast? A: Our current DNA extraction service is primarily for yeast samples only.
Please submit an inquiry with the APM team for DNA extraction evaluation if a customer has other fungi samples, such as rusts, smuts, mildews, molds, and mushrooms.
- Can we perform DNA extraction from viruses?
- A: No, we cannot extract DNA for viruses, including bacteriophages.
- Can we perform DNA extraction on other microbes such as protists and algae?
- A: No, we cannot extract DNA from protists and algae.
- What is the library size for the Microbial whole genome library?
- A: 350bp insert size for both PCR library and PCR free library as default.
Besides 350bp insert size library, are there any other choices for different library sizes? A: We can offer the below insert size library without any additional charge.
100-500bp, 100-350bp, 200-300bp, 200-400bp, 500bp. PCR-free library can’t perform 500bp insert size library. Please contact APM if you have other insert size about the additional charge needed.
- Can we perform library prep and sequencing for viruses’ samples?
- A: If the nucleic acid type of virus is double-stranded DNA or double-stranded cDNA; and not on the infection list, then we can accept by using microbial whole genome library and sequencing. If it is single-stranded or RNA, we won’t be able to perform WGS library construction. Please note that double-stranded cDNA will be considered as risky library preparation and sequencing.
- Can we perform assembly in our mWGS standard analysis or used assembled data for analysis?
- A: No, we cannot provide assembly in mWGS and is also unable to use assembled sequenced data for mapping with a reference genome.
- Can we offer 2 genomes comparison and provide variant calling information? A: No, we are unable to offer this type of analysis to the customer.
What kind of files should be provided by clients for variant calling and annotation (standard analysis)?
- A: If clients need standard analysis, the fasta file (genome file) and gff/gtf file (annotation file) are required. It is better to provide the link to the genome level.
- Can we provide our standard analysis for other microbes such as viruses and protists?
- A: It depends and we recommend submitting an inquiry to the APM team for an evaluation.
What if the customer is interested in obtaining information regarding antibiotic resistance or functional genes alongside variant calling? A: Microbial resequencing standard analysis can only provide variant calling but does not provide any assembly nor functional gene annotation. While bacteria draft map standard analysis can provide assembly and functional gene annotation but does not provide any variant calling information.
If the customer would like both variant calling information with functional gene annotation, we recommend the customer to consider doing both bacteria resequencing standard analysis and bacteria draft map standard analysis. The raw data sequenced is compatible for both analysis pipeline.
- Can we provide variant calling on an assembled genome?
- A: No, we can only provide variant calling on NGS fastq file type in our standard analysis for microbial resequencing. If the customer would like us to provide genome assembly, this can be done in “Bacteria Draft Map” analysis but no variant calling will be provided in “Bacteria Draft Map”.
- What is our experience with mapping rates?
- A: Our experience and recommended mapping rate is above 85%.
If the mapping rate is lower than 85%, how to proceed?
- A: If the mapping rate is lower than 85%, the client can change to another reference genome so that we can try mapping a second time for free.
The client can then choose the data with a better mapping rate reference to proceed with the subsequent analysis. However, we will need to charge an additional price of 40% of the standard analysis price per sample per time if the client would like to map more than twice.
If all the mapping rates are not good enough to proceed for subsequent standard analysis, the client can change to draft map analysis with an additional price. Please refer to the ‘bacteria genome draft map’ in the price list for more information.
Microbial PCR Product
This product is available only for clients that provide us PCR products with no barcode added, so 1 PCR product sample will require 1 PCR-free library. PCR products are for genotyping purposes and not for metabarcoding purposes. If customer has PCR products for metabarcoding purposes, please refer to the amplicon sequencing product manual.
## Sample Requirements
Library Type*
PCR Product Size
Amount (Qubit)
Volume
Concentration
Purity (NanoDropTM/Agarose Gel)
PCR-free library for PCR products (Single Library)
100-500bp**
≥ 1.5 μg
≥ 20 μL
≥ 60 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination
≥ 500bp***
≥ 3 μg
≥ 20 μL
≥ 60 ng/μL
- Note:
* Must confirm the sample’s lab destination and biosafety regulations prior to accepting any microbial samples!
** Please refer to FAQ 1 for more information on insert size and corresponding solutions.
** Default Workflow: Without fragmentation, and selection by gel-cutting with a recovery rate of about 20%.
*** Fragmentation and selection by gel-cutting, with a recovery rate of about 20%. Need to remark in Quotation about the expected library insert size if PCR product size above 500bp
Sequencing Strategy and Turnaround Time
Sequencing Strategy*
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
NovaSeq PE150
1G raw data* or more
15 working days
23 working days
NovaSeq PE250
1M Raw reads or more
15 working days
23 working days
- Note:
Please choose Novaseq PE150 or PE250 for sequencing based on the PCR product and library size. Data amount will vary depending on PCR product, library size, and project requirements.
Analysis Contents
Standard Analysis-Bacterial/ fungal
Software
Data quality control: filtering reads containing adapters or low-quality reads
Fastp
Alignment with reference
BWA, Sambamba, Samtools
SNP/InDel calling, annotation and statistics
GATK, ANNOVAR
SV calling, annotation and statistics
BreakDancer, ANNOVAR
CNV calling, annotation and statistics
Cnvnator, ANNOVAR
Variation Map of Whole Genome
Circos
Demo for Data Release Structure
Same as Microbial Genome Resequencing
## FAQ
*Please confirm whether the species is on the China-Directory of Human Pathogenic Microorganisms or not first. If yes, we cannot accept it since we can only perform this product in China lab.
- What is the special notice for PCR product as the starting material? A: Please see the chart below for more information.
What happens when the PCR product is below 100bp?
- A: We cannot accept this PCR product due to the disproportionate adapter reads sequenced during sequencing.
For PCR products that exceeds 500bp, what are the fragment sizes available for selection? A: We can offer the below insert size library without any additional charge.
100-500bp, 100-350bp, 200-300bp, 200-400bp, 350bp. The PCR-free library can’t perform a 500bp insert size library for PCR products. Please contact APM for the additional charge if you have another insert size of interest.
- Can we provide a mixed library for mWGS PCR products if these samples have barcodes on them?
- A: No, mixed libraries are only provided in amplicon sequencing. Each PCR product is used to build a single PCR-free library as the purpose of the library preparation and sequencing is for microbial whole genome sequencing.
- What is the difference between the PCR products for mWGS and amplicon sequencing?
- A: The main difference is that the PCR products for mWGS are amplified with primers for the purpose of genotyping specific primers. Whereas, the primers used in the PCR products for amplicon sequencing are for the purpose of metabarcoding (ie. Taxonomical identification) a metagenomic sample.
Bacteria Draft Map
Bacteria de novo sequencing determines the sequences of DNA bases of a novel bacteria and identify key genetic information for their possible applications through short-reads sequencing. This allows for a cost-effective method to identify key genetic information and their possible application in both pathogenicity and disease outcomes. Unfortunately, short-read sequencing often fails to resolve the repeated elements in the bacteria genome and is thus considered as an incomplete mapping of the novel organism.
DNA extraction
Sample types*
Species
Recommended Input
Replicates
Tube Recommendations
Transportations
Bacterial solution (log phase)
Bacteria**
≥ 4ml
2
Sterile, Pre-cooled
1.5/2.0ml EP Tube
Dry Ice
Bacterial cell pellet
Bacteria**
Centrifugation of corresponding bacterial solution
2
Sterile, Pre-cooled
1.5/2.0ml EP Tube
Dry Ice
- Note:
Must confirm the sample’s lab destination and biosafety regulations prior to accepting any microbial samples!
* Please check with the APM team on kit availability for any projects that will need DNA extraction in CSA lab. For more details, please refer to the Sample Extraction Service in the price list.
** Our DNA extraction from bacteria solution and cell pellet are limited to Gram-negative bacteria. For more information, please refer to FAQ 2.
## Sample Requirements
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/agarose gel)
Microbial whole genome library*
Genomic DNA
≥ 200 ng
≥ 20 μL
≥ 10 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination, no color
Microbial whole genome library
(PCR-free 350bp library)
Genomic DNA
≥ 1.2 μg
≥ 20 μL
≥ 10 ng/μL
- Note:
Please refer to FAQ.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 30 samples)
WOBI
WBI
Microbial whole genome library
NovaSeq PE150
100× (bacteria)
15 working days
30 working days
Analysis Contents
Standard Analysis
Software
Data quality control: filtering reads containing adapters or low-quality reads
Readfq, fqcheck, flash
Genome survey and Genome Assembly
meryl, gce, Genomeye, SPAdes, ABySS, CISA, Gapcloser, SOAp2
Genome Component Prediction:
(Coding gene, Repetitive sequences, Non-coding RNA, Genomic Island, Prophage, CRISPR)
GeneMarkS, TRF, RepeatMasker, tRNAscan-SE, rRNAmmer, blast, cmsearch, IslandPath-DIOMB, phiSpy, CRISPRdigger
Gene Function Annotation: *
(GO, KEGG, COG, NR, Pfam, TCDB, CAZy, TNSS, T3SS, PHI, VF, ARDB-CARD,
Swiss-Prot, Secretory Protein, Secondary Metabolism)
PfamScan, pfam2go, diamond, EffectiveT3, SignalP, TMHMM, antiSMASH
- Note:
Gene Function Annotation includes: GO (Gene Ontology), KEGG (Kyoto Encyclopedia of Genes and Genomes), COG (Cluster of Orthologou Groups of Proteins), NR (Non-redundant Protein Database), TCDB (Transporter Classification Database), Pfam (Proteins), Swiss-Prot (Proteins), CAZy (Carbohydrate-Active enZYmes Database), Secretory Protein (Secreted Proteins), TNSS and T3SS (Secretory and Effector Proteins), Secondary Meabolism (Secondary Metabolite), PHI (Pathogen Host Interactions), VF (Virulence Factors), ARDB-CARD (Antibiotic Resistance Gene).
Demo for Data Release Structure
## FAQ
*Please refer to the biosafety regulations for the various labs when talking with to the customer about any potential projects.
Question TypesQuestions to Ask the CustomerFollow-up ClarificationQuestionsPossible SolutionsProject Related QuestionsQ1. Do the customer have a reference genome?Yes, to Q1.1; No, to A1.1Q1.1 Even with a reference genome, does the customer require genome assembly? Yes, to A1.1; No, to A1.2A1.1. The customer can have an option of doing bacteria draft map or bacteria complete map.A1.2 We recommend the customer to dobacteria resequencing instead.Q2. What is the customer’s budget?Q2.1 Is the customer willing to consider bacteria complete map instead of bacteria draft map? Yes, to A2.1; No, to A2.2A2.1 Please refer to the PacBio Product Manual for more information on Bacteria complete map.A2.2 The customer can proceed for bacteria draft map but please note that it is still recommended for the customer to consider Bacteria Complete Map if theyhave the budget.Analysis Related QuestionsQ3. Is the customer interested in obtaining various variant results with their bacteria annotation results?Yes, to A3.1; No, to A3.2A3.1 They will need to do both bacteria resequencing analysis and bacteria draft map analysis.A3.2 Proceed with standard analysis forbacteria draft map.Question TypesQuestions to Ask the CustomerFollow-up ClarificationQuestionsPossible SolutionsProject Related QuestionsQ1. Do the customer have a reference genome?Yes, to Q1.1; No, to A1.1Q1.1 Even with a reference genome, does the customer require genome assembly? Yes, to A1.1; No, to A1.2A1.1. The customer can have an option of doing bacteria draft map or bacteria complete map.A1.2 We recommend the customer to dobacteria resequencing instead.Q2. What is the customer’s budget?Q2.1 Is the customer willing to consider bacteria complete map instead of bacteria draft map? Yes, to A2.1; No, to A2.2A2.1 Please refer to the PacBio Product Manual for more information on Bacteria complete map.A2.2 The customer can proceed for bacteria draft map but please note that it is still recommended for the customer to consider Bacteria Complete Map if theyhave the budget.Analysis Related QuestionsQ3. Is the customer interested in obtaining various variant results with their bacteria annotation results?Yes, to A3.1; No, to A3.2A3.1 They will need to do both bacteria resequencing analysis and bacteria draft map analysis.A3.2 Proceed with standard analysis forbacteria draft map.What are some of the questions that you ask when a customer is interested in bacteria de novo analysis? A: Please refer to the table below for example questions for customers with new microbial WGS inquiries.
Question Types
Questions to Ask the Customer
Follow-up Clarification
Questions
Possible Solutions
Project Related Questions
Q1. Do the customer have a reference genome?
Yes, to Q1.1; No, to A1.1
Q1.1 Even with a reference genome, does the customer require genome assembly? Yes, to A1.1; No, to A1.2
A1.1. The customer can have an option of doing bacteria draft map or bacteria complete map.
A1.2 We recommend the customer to do
bacteria resequencing instead.
Q2. What is the customer’s budget?
Q2.1 Is the customer willing to consider bacteria complete map instead of bacteria draft map? Yes, to A2.1; No, to A2.2
A2.1 Please refer to the PacBio Product Manual for more information on Bacteria complete map.
A2.2 The customer can proceed for bacteria draft map but please note that it is still recommended for the customer to consider Bacteria Complete Map if they
have the budget.
Analysis Related Questions
Q3. Is the customer interested in obtaining various variant results with their bacteria annotation results?
Yes, to A3.1; No, to A3.2
A3.1 They will need to do both bacteria resequencing analysis and bacteria draft map analysis.
A3.2 Proceed with standard analysis for
bacteria draft map.
Question Types
Questions to Ask the Customer
Follow-up Clarification
Questions
Possible Solutions
Project Related Questions
Q1. Do the customer have a reference genome?
Yes, to Q1.1; No, to A1.1
Q1.1 Even with a reference genome, does the customer require genome assembly? Yes, to A1.1; No, to A1.2
A1.1. The customer can have an option of doing bacteria draft map or bacteria complete map.
A1.2 We recommend the customer to do
bacteria resequencing instead.
Q2. What is the customer’s budget?
Q2.1 Is the customer willing to consider bacteria complete map instead of bacteria draft map? Yes, to A2.1; No, to A2.2
A2.1 Please refer to the PacBio Product Manual for more information on Bacteria complete map.
A2.2 The customer can proceed for bacteria draft map but please note that it is still recommended for the customer to consider Bacteria Complete Map if they
have the budget.
Analysis Related Questions
Q3. Is the customer interested in obtaining various variant results with their bacteria annotation results?
Yes, to A3.1; No, to A3.2
A3.1 They will need to do both bacteria resequencing analysis and bacteria draft map analysis.
A3.2 Proceed with standard analysis for
bacteria draft map.
- Can the customer proceed with using the same sequenced data from bacteria resequencing for bacteria draft map analysis? A: Yes, the sequenced data can be used for bacteria draft map analysis as well.
- Can we compare two draft map analysis or two assembled genomes for customized analysis?
- A: No, the bacteria draft map analysis pipeline is meant for de novo analysis and is not meant for a comparison of two assembled genomes.
In some sense, this pipeline is “borrowed” for customer’s that have a reference genome but would like to receive annotation results as well. However, it is never meant for variant analysis.
- Can we provide variant analysis results from bacteria draft map analysis?
- A: No, if the customer would like to receive variant analysis, they will need to do bacteria resequencing standard analysis.
Microbial resequencing standard analysis can only provide variant calling but does not provide any assembly nor functional gene annotation. While bacteria draft map standard analysis can provide assembly and functional gene annotation but does not provide any variant calling information.
Fungal Survey
Fungal survey is only meant for a quick genomic survey in regards to the genome’s GC content, genome size and purity. This is the primary reason as to why it may be paired with Fungal Fine Map. However, it is not meant for providing any further information to the genome. Thus, if a customer is interested in doing de novo analysis of their fungi samples, please proceed with Fungal Fine Map instead.
## Sample Requirements
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/agarose gel)
Microbial whole genome library*
Genomic DNA
≥ 200 ng
≥ 20 μL
≥ 10 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination, no color
Microbial whole genome library (PCR-free 350bp library)
Genomic DNA
≥ 1.2 μg
≥ 20 μL
≥ 10 ng/μL
- Note:
* Please refer to FAQ.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 30 samples)
WOBI
WBI
Microbial whole genome library
NovaSeq PE150
100× or above (fungus) at least 1Gb data per library
15 working days
30 working days
Analysis Contents
Standard Analysis
Software
Data quality control: filtering reads containing adapters or low-quality reads
Readfq,fqcheck, flash
Genome survey and Genome Assembly
meryl, gce, Genomeye, SOAPdenovo, Gapcloser, SOAP2
Demo for Data Release Structure
## FAQ
*Please refer to the biosafety regulations for the various labs when talking with to the customer about any potential projects.
- Can we provide any other genome information or annotation results with fungal survey?
- A: No, the fungal survey analysis is only meant as a genomic survey and is typically used as a complementary analysis with fungal fine map instead.
What if my customer would like to do de novo analysis for their fungi samples but do not have the budget for fungal fine map?
- A: We can offer fungal draft map for this customer but please note that the results will not be comparable to the fungal fine map. Please submit an inquiry to the APM for an evaluation.
What if my customer would like to receive annotation results alongside their fungal resequencing results? A: We can offer fungal draft map for this customer. Please submit an inquiry to the APM for an evaluation.
Novogene Product Manual
Plant & Animal Whole Genome Sequencing
AMEA 2024.11
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclose to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
9 PAWGS AMEA Product Manual-2024 V1.0
Revision Number
V3.0
Issue Date
November 25, 2024
Prepared by
Liu Rui
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Overall renewed for this version.
Update sample requirements, turnaround time and products information of all types of service.
Liu Rui Liang Yan
August 29, 2023
2024 V1.0
Page 4: Sample requirement update
Page 4~14: Software updates of SNP/ InDel variant calling Page 10-FAQ 1: Insert size update
Page 20-FAQ 5: Customized GBS evaluation update
Liu Rui Liang Yan
November 25, 2024
Content
Plant & Animal Whole Genome Resequencing4
## Sample Requirements4
Sequencing Strategy and Turnaround Time4
Analysis Contents5
FAQ of PAWGS8
SNP Genotyping15
## Sample Requirements15
Sequencing Strategy and Turnaround Time15
Analysis Contents15
FAQ of SNP Genotyping (GBS)16
Whole genome off-target detection19
## Sample Requirements19
Sequencing Strategy and Turnaround Time19
Analysis Contents19
FAQ of whole genome off-target detection20
Plant & Animal Whole Genome Resequencing
Whole genome sequencing (WGS) provides the most comprehensive collection of genetic information of individuals or populations. The identification of variation information such as Single Nucleotide Polymorphism (SNP), Insertion and Deletion (InDel), Copy Number Variation (CNV), and structural variation (SV) obtained through WGS are the core steps of various research areas, like population genetics research and genome-wide association studies (GWAS) which help researchers investigate the causes of diseases, select proper plants or animals for agricultural breeding programs, and to identify common genetic variations among populations.
## Sample Requirements
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/Agarose Gel)
Plant and Animal Whole Genome Library
Genomic DNA
≥ 100 ng
≥ 20 μL
≥ 5 ng/μL
OD260/280 = 1.8-2.0, no
degradation, no contamination
Plant and Animal Whole Genome PCR-Free Library
Genomic DNA
≥ 1.2 μg
≥ 20 μL
≥ 50 ng/μL
OD260/280 = 1.8-2.0,
no degradation, no contamination
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 30samples)
WOBI
WBI
Plant and Animal Whole Genome Library
NovaSeq PE150
30×
15 working days
22 working days
Plant and Animal Whole Genome Library
NovaSeq X Plus PE150
30×
15 working days
22 working days
Plant and Animal Whole Genome Library
MGI DNBseq PE150
30×
20 working days
25 working days
Analysis Contents
P&A WGS Standard Analysis
Software
Data quality control: filtering reads containing adapter or with low quality
Fastp
Alignment with reference genome, statistics of sequencing depth and coverage
BWA, samtools
Variant (SNP, InDel) calling, annotation and statistics*
bcftools/GATK*, ANNOVAR
- Note:
* Bcftools is the default software for variant calling. More details please refer to FAQ8.
- Note: Advanced analysis includes but not limited to the following contents. Please refer to price list for ‘P&A WGS: SNP+InDel+SV+CNV analysis’.
P&A WGS Advanced Analysis
Software
Data quality control: filtering reads containing adapter or with low quality
Fastp
Alignment with reference genome, statistics of sequencing depth and coverage
BWA, samtools
Variant (SNP, InDel) calling, annotation and statistics
bcftools/GATK*, ANNOVAR
SV calling, annotation and statistics
Breakdancer, ANNOVAR
CNV calling, annotation and statistics
CNVnator, ANNOVAR
- Note:
* Bcftools is the default software for SNP/InDel variant calling. More details please refer to FAQ8.
- Note: For ‘Customized Analysis’, please check with APM on a case-by-case bias to obtain detailed information about the analysis content and pricing. The list of analysis content provided below is only for reference. The actual analysis may vary depending on the specific research purpose of customers. They have flexibility to choose one or more analysis items based on their research. These analysis are not part of a standard package automatically delivered to customers.
P&A WGS Customized Analysis
Software
*Somatic SNP/InDel (paired samples)
MuTect
**Somatic SV (paired samples)
Delly
Somatic CNV (paired samples)
Control-FREEC
- Note:
* Results of standard analysis (SNP and InDel detection) is required.
** Results of advanced analysis (SV detection) is required.
Customized Analysis- Variation Detection BSA
Software
Data quality control: filtering reads containing adapter or with low quality
Fastp
Alignment with reference genome, statistics of sequencing depth and coverage
BWA, samtools
SNP/InDel joint calling, annotation and statistic
GATK, ANNOVAR
SNP-index calculation
Candidate SNP/InDel, candidate region filtering
Large effect SNP/InDel annotation
Customized Analysis- Genome-wide association study (GWAS)
Software
Note
Data quality control: filtering reads containing adapter or with low quality
Fastp
Alignment with reference genome, statistics of sequencing depth and coverage
BWA, samtools
Variant (SNP, InDel) calling, annotation and statistics
bcftools/GATK, ANNOVAR
Population Structure: Phylogenetic tree
Principal component analysis (PCA)
TreeBest GCTA software
Optional:
Provided only upon customer request.
Linkage disequilibrium (LD)
PopLDdecay
Gene enrichment analysis (GO & KEGG)
GEMMA
Genome-wide association study (GWAS)
EMMAX/GEMMA/TASSEL/GAPIT
Customized Analysis- Population Genetics Analysis
Software
Note
Data quality control: filtering reads containing adapter or with low quality
Fastp
Alignment with reference genome, statistics of sequencing depth and coverage
BWA, samtools
Variant (SNP, InDel) calling, annotation and statistics
bcftools/GATK, ANNOVAR
Population Structure： Phylogenetic tree
Principal component analysis PCA
Genetic Structure
TreeBest GCTA software Admixture
Optional:
Provided only upon customer request.
Linkage disequilibrium (LD)
PopLDdecay
Selective Sweep Analysis：
Fixation statistics (Fst) – Comparison Nucleotide diversity (θπ) – Comparison
Tajima'D
VCFtools
Demographic history：
Historical effective population size
PSMC
Gene flow
TreeMix
FAQ of PAWGS
- What is the library size for the plant and animal whole genome library?
- A: Our standard library size is ~350bp for both PCR library and PCR free library. However, please note that 350bp is a range, but not an exact value. During the library preparation, we implement a strict quality management process to ensure the library size remains within the range of 320bp-350bp. Variations in sample quality and reagent batches may cause slight differences in insert size between batches. Such variations are normal and do not affect data quality or the accuracy of downstream analysis.
If the customer specifies the library size, can we offer the library preparation service?
- A: We can offer the service for the following insert size without any additional charges. If customers have other requests, please check with APM team. 100-500bp, 100-350bp, 200-300bp, 200-400bp, 500bp (This is only for common libraries with PCR amplification. We can’t accept 500bp insert for PCR-free libraries)
- Can we offer library preparation and sequencing service for FFPE DNA samples?
- A: The full name of FFPE is Formalin-fixed, paraffin-embedded. We can only accept mouse FFPE samples now.
Here is the sample requirement:
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/Agarose Gel)
Plant and Animal Whole Genome Library
FFPE DNA
≥ 800 ng (recommended)
≥ 400 ng (required)
≥ 15 μL
≥ 10 ng/μL
Fragments longer than 1000 bp
Considering the difficulties of extracting DNA from FFPE samples, we can accept samples below the sample requirements. Based on our previous
experiences, the lowest amount of FFPE DNA is > 200ng with a fragment length > 300bp. However, we can only provide risky library preparation, and we can’t guarantee the results. Please inform the client about the risk before the offer. Additionally, only SNP/INDEL calling analysis will be provided. Please charge an additional 100USD per sample for library prep.
- Can we provide DNBSEQ platform for PAWGS?
- A: Yes, we offer DNBSEQ-T7 sequencing services for PAWGS. Both standard whole genome libraries and PCR-free libraries are supported, except for FFPE DNA and cfDNA/ctDNA samples. The sample requirements are the same as those for the Illumina NovaSeq platform, while the TAT may be slightly longer with the DNBSEQ-T7 platform.
Which file should be provided by clients for WGS related BI analysis?
- A: Before analysis, it is essential for customers to provide a reference genome, which should include a fasta file (genome file) and a gff/gtf file (annotation file). Both download links and file packages work for us. Further, we highly recommend providing a more complete version of genome and annotation, as they will significantly impact the accuracy and reliability of the analysis results.
- Can we accept PCR product for plant and animal whole genome sequencing?
- A: Yes, please use PCR-free library preparation method and choose Plant and Animal PCR Product Whole Genome Sequencing (WOBI) in SFDC. For PCR product size larger than 500bp, we highly recommend interrupting within the 100-500bp size or around 350bp library size. The lab can assist with this process if needed. Please include the PCR product size and details on how to proceed in the quotation. Additionally, please note that demultiplexing service is not available.
Here is the sample requirement:
Library Type
Sample Type
Amount (Qubit®)
Volume
Concentration
Purity (Qubit/Agarose Gel)
PCR-free library
PCR product
≥ 1.5 μg
≥ 20 μL
≥ 60 ng/μL
OD260/280=1.8-2.0;
no degradation, no contamination
- How to search reference genome?
- A: (1) NCBI (National Center for Biotechnology Information): https://www.ncbi.nlm.nih.gov
-Choose “genome” database and put in the species name.
-The genome information will be listed here. Click browse all genome can get the information of different genome version.
(2) Ensemble database: http://asia.ensembl.org/index.html
-Check the level of genome assembles, such as contig level, scaffold level or chromosome level. Generally, the genome assembles to scaffold level or chromosome level is more reliable.
-We need to find the GFF or GTF annotation file and evaluate the completeness of gene annotation. The annotation file needs to have annotation information of gene, script, CDs and exon areas (at least exon or CDs. If there is no exon, a CDs will be regarded as an exon for analysis). If the above information is complete and available, the preliminary evaluation of this reference genome can be used.
Which software do we use for variant calling?
- A: Different software tools are used for different types of variants. For more details, please refer to the analysis content. For SNP/InDel variant calling (excluding BSA analysis) software is bcftools. However, if clients specifically request to use GATK for joint calling, we can accommodate this request. Please check with the APM team regarding the additional cost. Kindly note that GATK requires a high-quality reference genome to ensure optimal performance and accuracy.
If clients have an exogenous DNA insertion to a plant/ animal genome, and want to identify the insertion loci in the plant/ animal genome, what is our solution?
- A: It’s highly recommended to use PacBio HiFi WGS instead, 15-20X depth. If customers insist on using NGS WGS, we can still provide the service accordingly. In both cases, clients need to provide reference genome and DNA insertion sequence. We will then combine the sequence of insertion DNA and reference genome to create a combined reference genome for variants calling. The loci of insert DNA can be detected by SV calling. However, we can't provide a detailed insertion number and accurate loci.
- What is the basic information about BSA analysis?
- A: The BSA (Bulked Segregation Analysis) used for the target trait was mapped to a region of the chromosome at the genome level, and the genes associated with the target trait were annotated.
-Trait selection: A pair of phenotypic extreme traits.
-Sample requirement: Family samples with reference genome.
-Sample amount: Two parental samples and two offspring pools of 25 samples each with relative traits.
-The process of material construction: For example, two homozygous parents with relative traits were crossed to obtain F1 generation. F1 generation was self-crossbred to obtain F2 generation, and individuals with phenotypic extreme traits were selected from F2 generation and mixed into the corresponding offspring pool of two extreme traits.
-The relationship between samples: For example, it would be better if the parental samples are two homozygous samples with relative traits, and offspring samples is selected from F2.
-Recommended sequence depth: at less 15× for each parent sample and at less 25× for each offspring pool.
-Please confirm with clients about the process of material construction, the relationship between parent and offspring, the concern traits, and the research purpose, which are vital for evaluation whether the samples are suitable for BSA analysis or not.
- What is the basic information about GWAS analysis?
- A: -Research purpose: Genome-wide SNP markers were developed through high-throughput sequencing of the population, and association analysis was performed combining with phenotypic traits data to find genetic markers or candidate gene loci associated with the target traits. GWAS can locate multiple traits at one time, with high efficiency and strong applicability.
-Sample requirement: GWAS is suitable for natural populations with reference genome.
-Sample amount: at least 300.
-Phenotypic characterization: It is suggested to select high heritability traits for target traits. The clearer the phenotypic record of the trait, the better
the subsequent analysis, including the record of the trait itself and the record of environmental conditions.
-Sequence strategy: at least 10× for each sample.
-Usually, we use bcftools to do joint calling. If clients need the GATK software to perform joint calling, please contact APM team for additional charge as GATK will consume more resources.
- What is the basic information about Population Genetics analysis?
- A: -Research purpose: The same species under different living conditions may form different subspecies or subgroups due to natural selection, artificial domestication, genetic drift, etc. The study of population evolution is to trace and expose this evolutionary process.
-Sample requirement: Subgroups of natural populations with reference genomes.
-Sample amount: At least three subgroups/ subspecies, with at least 10 samples per subgroup (animals ≥10, plants ≥15). The overall recommendation is not less than 30 samples.
-Sequence strategy: at least 10× for each sample.
-Usually, we use bcftools to do joint calling. If clients need the GATK software to perform joint calling, please contact APM team for additional charge as GATK will consume more resources.
SNP Genotyping
GBS (Genotyping-by-Sequencing) is a common Reduced-Representation Genome Sequencing technique in which genomic DNA is enzymatically digested and then the ends of the fragment are sequencing in high throughput. GBS technology can flexibly adjust the number of tags required to capture the restriction sites base research purpose, thus controlling the range of the capture sequence. The GBS can reduce the complexity of the genome with lower data amount, simplify the operation and save the cost, which is especially suitable for large amounts of samples.
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity (Qubit/Agarose Gel)
Genotyping by Sequencing (GBS) library
Genomic DNA
≥ 600 ng
≥ 20 μL
≥ 20 ng/μL
OD260/280 = 1.8-2.0
No degradation, no RNA contamination
Sequencing Strategy and Turnaround Time
Sequencing Strategy
Recommended data
Turnaround Time (≤ 50 sample)
WOBI
WBI
NovaSeq PE150
APM evaluation before quotation
25 working days
33 working days
Analysis Contents
Standard Analysis (With Reference)
Software
Data quality control: filtering reads containing adapter or with low quality
Fastp
Mapping: Alignment with reference genome, statistics of sequencing depth and coverage
BWA, samtools
SNP/InDel calling, annotation and statistics
samtools, ANNOVAR
SNP genotyping analysis
-
Tags statistic
-
Standard Analysis (Without Reference)
Software
Data quality control: filtering reads containing adapter or with low quality
Fastp
Merge paired-end reads into one sequence
Vsearch v2.6.2
Mapping: Alignment with reference genome, statistics of sequencing depth and coverage
BWA, Samtools
SNP/InDel calling
samtools, ANNOVAR
SNP genotyping analysis
-
Tags statistic
-
FAQ of SNP Genotyping (GBS)
- How to check whether the species have the GBS evaluation result?
- A: Please check “AMEA Enzyme evaluation results for GBS_UTD 2023” in Wedrive. You can also get access through the link below. https://doc.weixin.qq.com/sheet/e3_AGsAmgYdAN0d8IZ7MK6RdGTzvm422?scode=AJgAAQcaAAwjU8iB79AGsAmgYdAN0&tab=BB08J2
Notice:
-Please pay attention to the reference genome and data amount. If customers specify a different genome or data amount, we have to re-evaluate.
-Special situations/enzymes are marked in yellow. Please check with APM first.
What information is required when inquiry from APM about the enzyme and data output? A: A1. Species with Latin names.
A2. Sample number (Please refer to price list remark as different sample numbers may have varying prices).
A3. Reference genome link and genome size: Please verify the availability of the reference genome before submitting your inquiry. If customers do not provide a reference genome, we will select one from public databases. If a reference genome is not available in these databases, customers will need to provide their own reference genome or specify the name of a closely related species with an available reference genome.
A4. Client’s required tags number: If client wants us to recommend, then there is no need to indicate.
A5. Any other special requests from the customers. For example, if they previously conducted GBS projects with us and would like to maintain the same strategy, or if they would like to specify the enzyme to be used.
What data size we can promise to client?
- A: We promise Mb raw data (or Gb data if genome size is huge) for ‘Pass’ grade samples.
What does the special information need to pay attention to?
- A: 1) The minimum sample quantity should be 6. If not, the price will be much higher, and please reject the case.
The price stays the same without bioinformatics.
For data amount less than 120M raw base, the price stays the same with 120M raw base.
If customers specify, they are parent samples, isolated parent library preparation was recommended, and the package price will be 3X using this strategy.
If customers specify an enzyme, can we offer customized service?
- A: We use a double-enzyme protocol, where the 1st enzyme, Msel, is fixed and cannot be customized. However, if customers require a customized 2nd enzyme for their specific needs, we first need to confirm its availability in our lab. If the enzyme is available, the APM team will assess its suitability for the customer’s target species. If we don’t have the enzyme, we are unable to provide the service unless the customer supplies the enzyme. In this
case, please check with APM team in details. Enzymes available in our lab: NlaIII, HaeIII, EcoRI, HaeII, MspI.
After our evaluation, if client wants to change the data size, what should Sales/ TS do?
- A: Please email to APM, and we will ask BI team to re-evaluate and give you the revised enzyme.
For different GBS enzyme digestion combinations, different fragment numbers and fragment sizes will be obtained, which will affect the amount of data. Therefore, if the amount of data is changed, the corresponding enzyme digestion combination may change accordingly. Data analysis results may also be affected due to data amount and enzyme change.
- Can we offer RAD or ddRAD sequencing?
- A: Sorry, we currently do not offer RAD-seq service. However, our GBS service provides a cost-effective alternative to RAD-seq. If customers require more in-depth analysis, they can also choose our WGS service. If customers request ddRAD-seq, we can explain that our GBS workflow is technically the same as ddRAD-seq as we use double enzyme digestion protocol. This enables us to achieve similar results with ddRAD-seq. Customers can choose our GBS service instead.
- Can we use GBS data to perform GWAS or BSA analysis?
- A: Sorry, we can’t. Due to the low genome coverage of GBS, the result will not be good. We suggest PAWGS for GWAS and BSA analysis instead.
Whole genome off-target detection
Off-target detection is a routine practice for samples after CRISPR/Cas9 knockout experiments. In the case of knockout samples, whole genome sequencing can be utilized to detect off-target information by scanning regions that are homologous to the sgRNA sequence.
## Sample Requirements
Sample Type
Required
Volume
Concentration
Purity (Qubit/Agarose gel)
Genomic DNA*
≥ 100 ng
≥ 20 μL
≥ 5 ng/μL
OD260/280 = 1.8-2.0, no degradation, no
contamination
- Note:
* Microbial samples are not acceptable.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 10 samples; ≤ 150G/sample)
Without analysis
With standard analysis
Plant and Animal Whole Genome Library
NovaSeq PE150
Case > 50×
15 working days
30 working days
Control > 30×
Analysis Contents
Standard Analysis (Whole genome knockout off-target detection)
Data quality control
Sequencing depth and coverage statistics
SNP/InDel variant detection statistics, variant site distribution and functional annotations in different regions of the genome
Unique SNP/InDel detection, SNP mutation type statistics, InDel length distribution statistics
Screening of sgRNA homologous regions, SNP/InDel statistics of homologous regions
Circos diagram of sgRNA homology region
FAQ of whole genome off-target detection
Is it necessary to send both control and case sample?
- A: Case samples refer to samples that have undergone CRISPR modification, while control samples refer to those that have not been modified. It is essential to send both case and control samples when the client wants to perform whole genome knockout off-target detection.
Which kind of sample we can’t accept? A: Microbial samples are not acceptable.
Does sgRNA sequence need to be provided for analysis? A: Yes, the sgRNA sequence is required for analysis.
What are the differences between whole genome off-target detection and CRISPR screening?
ServiceWhole Genome Off-target detectionCRISPR ScreeningSample typeGenomics DNAPCR product (sgRNA library)Do we have bioinformatics analysis?YesNoServiceWhole Genome Off-target detectionCRISPR ScreeningSample typeGenomics DNAPCR product (sgRNA library)Do we have bioinformatics analysis?YesNoA: Here, we outline the distinctions between whole genome off-target detection and CRISPR screening. We are capable of handling library preparation for both scenarios. However, we can only provide analysis services for whole genome off-target detection.
Service
Whole Genome Off-target detection
CRISPR Screening
Sample type
Genomics DNA
PCR product (sgRNA library)
Do we have bioinformatics analysis?
Yes
No
Service
Whole Genome Off-target detection
CRISPR Screening
Sample type
Genomics DNA
PCR product (sgRNA library)
Do we have bioinformatics analysis?
Yes
No
Research purpose
Off-target detection
CRISPR screening is a widely used method to investigate gene sets that interact with specific phenotypes. In such cases, researchers often design multiple sgRNAs. Following positive or negative cells selection experiments, CRISPR screening is employed to screen the changes of sgRNA
libraries.
Analysis method
Align sequences with reference genome.
Detect SNP/ InDel and identify off-target information.
Align sequences with sgRNA libraries. Determine the
conditions and proportions of each sgRNA within the library.
Novogene Product Manual
Epigenomics Sequencing
AMEA 2025.09
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
10 Epigenomics Sequencing AMEA Product Manual
Revision Number
2025 V2.0
Issue Date
29 September, 2025
Prepared by
Liu Rui
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.1
Pg 9 – FAQ 4. Library preparation and sequencing of Cut & Run enriched DNA Pg 12 – Samples Requirements. MeRIP enriched RNA change from 40ng to 50ng
Tianran Shi
11 April, 2023
2025 V1.0
Pg 5 - ChIP-seq analysis update
Pg 10 - RIP-seq, MeRIP-seq sample requirement update Pg 25 - WGBS analysis update
Rui Liu
27 January,
2025
2025 V2.0
Sample requirement update
Rui Liu
29 September,
2025
ChIP-Seq
Chromatin Immuno-precipitation Sequencing (ChIP-Seq) provides genome-wide profiling of DNA targets for histone modification, transcription factors, and other DNA-associated proteins. It combines the selectivity of chromatin immuno-precipitation (ChIP) to recover specific protein-DNA complexes, with the power of next-generation sequencing (NGS) for high-throughput sequencing of the recovered DNA. Additionally, because the protein-DNA complexes are recovered from living cells, binding sites can be compared in different cell types and tissues, or under different conditions.
Principle
An overview of a ChIP–Seq experiment: Using chromatin immunoprecipitation (ChIP) followed by massively parallel sequencing, the specific DNA sites that interact with transcription factors or other chromatin-associated proteins (non-histone ChIP) and sites that correspond to modified nucleosomes (histone ChIP) can be profiled (doi:10. 1038/nrg2641).
Novogene ChIP-Seq workflow.
Sample Requirement
Sample Type
Amount
Volume
Concentration
Note
Enriched DNA Sample
≥ 20 ng
≥ 20 μL
≥ 1 ng/μL
Main peak of 100 bp-500 bp
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
ChIP-Seq Library
PE150
3 Gb/6 Gb
15 working days
25 working days
Analysis Content
ChIP-Seq Standard Analysis
Software
Data quality control (get rid of reads containing adapter or with low quality; Q20, Q30, error rate distribution, GC distribution, total bases)
FastQC
Mapping onto reference genome (mapping rate, reads distribution)
BWA
Peak calling
MACS2
Motif prediction
homer
Peak annotation (downstream or overlapping gene, TSS)
ChIPseeker
Functional analysis of peak-associated genes (Gene Ontology, KEGG pathway)
GOSeq; KOBAS
Differential analysis
diffBind
Visualization of ChIP-seq data
/
## FAQ
- What is the library size for ChIP seq library?
- A: 100-500 bp (detailed distribution is dependent on sample peak distribution).
- What is Input sample and why it is essential for ChIP-Seq projects?
- A: Input control is essential in IP-seq experiments. After DNA fragmentation, we need to take part of the broken chromatin as input control before immunoprecipitation. During data analysis, we can eliminate the background noise on the basis of the input control (to verify the effect of chromatin breakage and the effect of IP in the entire experiment). IP sample refers to cross-linked DNA-protein complexes using an antibody against the protein of interest followed by incubation and centrifugation to obtain immunoprecipitation.
It is recommended to have a corresponding input sample for each IP sample (i.e., one pair of Input and IP samples). Replicate IP samples can share the same input sample. Library preparation and sequencing will be performed for both input and IP samples. However, please note that only the analysis results of the IP samples will be included in the analysis report. The input samples are directly involved in eliminating the background noise of the IP samples.
- What is the requirement for ChIP seq analysis?
- A: For ChIP seq analysis and other IP products, the species must have reference genome with complete annotation (e.g. exon, intron, CDS) and the species must be diploid.
What are the differences among ChIP seq, Cut&Run and Cut&Tag?
- A: CUT&Tag, which is short for Cleavage Under Targets and Tagmentation, is a molecular biology method that researchers use to investigate interactions between proteins and DNA and to identify DNA binding sites for their protein of interest. Although CUT&Tag is similar in some ways to ChIP assays, the starting material for CUT&Tag is live permeabilized cells or isolated nuclei rather than the cells or tissue that are cross-linked with formaldehyde that are used in ChIP.
CUT&RUN sequencing, also known as cleavage under targets and release using nuclease. CUT&RUN sequencing combines antibody-targeted controlled cleavage by micrococcal nuclease with massively parallel DNA sequencing to identify the binding sites of DNA associated proteins.
For CUT & RUN enriched DNA, we can try ChIP library prep process with risk, but it’s not meant to CUT&RUN, we can’t guarantee the success of library prep and results. We are unable to provide data analysis for CUT & RUN data.
In contrast to ChIP, CUT&Tag and CUT&RUN don’t require cells to be cracked open and their DNA and chromatin to be broken into pieces. Instead, cells stay intact, making the approach applicable to single-cell analyses, including projects like the Human Cell Atlas.
Novogene offers Cun&Tag product, please contact product manager for more details.
What are the successful experiences of Novogene’s projects?
- A: Animal: Human, Mouse, Rat, Zebrafish, Bee. Plant: Rice, Apple, Arabidopsis, Citrus, Rapeseed, Wheat, Tomato, Grape, Pepper, Tea Tree, Tobacco.
RIP-Seq and MeRIP-Seq
Protein-RNA interactions play important roles in multiple post-transcriptional regulation processes such as RNA cleavage, transport, sequence editing, intracellular localization and translational control. RNA immunoprecipitation (RIP) can be used to detect the association of individual proteins with specific nucleic acids. RNA immunoprecipitation sequencing (RIP-Seq) is a revolutionary technology that reveals the interaction of RNA and RNA-binding proteins at the genome-wide level. RIP-Seq maps the sites at which proteins are bound to the RNA and provides single-base resolution of protein-bound RNA.
MeRIP-seq stands for methylated RNA immunoprecipitation sequencing, which is a method for detection of post-transcriptional RNA modifications. It is also called m6A-seq. In this method, m6A-specific antibodies are used to immunoprecipitate RNA. RNA is then reverse transcribed to cDNA and sequenced. Deep sequencing provides high resolution reads of m6A-methylated RNA.
Principle
Schematic representation of native and cross-linked RIP protocols (doi:10.1007/978-1-4939-6380-5_7).
Sample Requirement
Product
Sample Type*
Amount
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
Note
RIP-Seq
Enriched RNA (after rRNA depletion)
≥ 30 ng
≥ 30 μL
≥ 1 ng/μL
Main peak ≥ 80 bp
It is recommended that customers remove the rRNA prior to sample submission. Please check with the customer and indicate in SIF that the rRNA has already been removed.
Enriched RNA (Novogene lab to perform the rRNA depletion)
≥ 55 ng
≥ 50 μL
≥ 1 ng/μL
Main peak ≥ 80 bp
If the customer does not perform rRNA depletion, Novogene can provide the service.
Human, mouse, and Arabidopsis sample: Qualified samples will be classified as PASS.
Other species: All samples will be classified as HOLD or FAIL, based on their quality.
MeRIP-
Seq
Enriched RNA (Customers remove rRNA)
≥ 30 ng
≥ 30 μL
≥ 1 ng/μL
Main peak ≥ 80bp
If the customer provides enriched RNA, please proceed with RIP-Seq for library preparation and sequencing.
Total RNA
≥ 30 μg
≥ 600 μL
≥ 50 ng/μL
RIN ≥ 5 with flat baseline;
no degradation; no contamination.
If the customer provides total RNA, Novogene will perform the m⁶A IP service.
Total RNA (low input)
≥ 2 μg
≥ 40 μL
≥ 50 ng/μL
RIN ≥ 5 with flat baseline; no degradation;
no contamination.
Only for human and mouse.
- Note:
*Sample Type: Please verify the sample type during the pre-sale stage. For enriched RNA samples, confirm with the customer whether rRNA removal and fragmentation have been performed beforehand. This information should also be clearly noted in SIF. The PM team need to arrange the appropriate QC and experiments based on this information.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 30 samples)
WOBI
WBI
RIP-Seq library
PE150
3 Gb/6 Gb
45 working days
50 working days
MeRIP-Seq library
PE150
6 Gb
45 working days
55 working days
Analysis Content
RIP-Seq/MeRIP-Seq Standard Analysis
Software
Data quality control (removal of reads containing adapter or with low quality; Q20, Q30, error rate distribution, GC distribution, total bases)
FastQC
Mapping to reference genome (mapping rate, reads distribution, rRNA content)
BWA
Peak calling
MACS2
Motif prediction
MEME
Peak annotation (downstream or overlapping gene, peak distribution in functional region of gene and transcript)
PeakAnnotator
Functional analysis of peak-associated genes (Gene Ontology, KEGG pathway)
GOSeq, KOBAS
Differential analysis
diffBind
Visualization of RIP-seq data
/
## FAQ
For MeRIP-seq, can data from normal library and low input library be analyzed together?
- A: No. They can only be analyzed separately since they have undergone different library preparation processes.
Does the customer need to remove rRNA by themselves if they choose normal MeRIP library?
- A: We strongly suggest customers do rRNA depletion by themselves, because the proportion of rRNA is more than 80%, it will seriously affect the amount of effective data obtained by subsequent sequencing.
Does the customer need to do RNA shearing in the IP experiment?
- A: Customer can do RNA shearing during IP experiments, but the fragments should be no less than 200bp. If the customer didn’t do RNA shearing, Novogene will do RNA shearing during library preparation process. Please indicate when submitting the sample information.
Why RIP-Seq and MeRIP-Seq need to have both IP and Input sample?
- A: In the IP experiment, the IP samples were specifically enriched with antibody, and the input was only fragmented RNA as the control to reduce the background noise. Library for both IP and Input samples needed to be prepared and sequenced at the same time. Peak calling needs to integrate the data of two samples and use input data to exclude peaks with high background expression level or nonspecific binding, so as to improve the accuracy.
It is better to have the corresponding input sample for each IP sample (i.e., one pair of Input and IP sample). Replicate samples can share the same input sample. Library preparation and sequencing will be done for both Input and IP samples. Note that there will be only one analysis result for one pair of samples.
- What is the requirement for RIP/MeRIP analysis?
- A: -For RIP-Seq and MeRIP analysis, the species must have reference genome with complete annotation (e.g. exon, intron, CDS).
-RIP-Seq and MeRIP-Seq can’t analyze ncRNA.
-Data from low input MeRIP library prep method can’t be analyzed with normal library prep method.
-For RIP-Seq&mRNA or MeRIP-Seq co-analysis, please contact product manager.
What are the successful experiences of Novogene’s projects? A: Human, Mouse, Zebrafish, Pig, Tomato, Corn, Arabidopsis, etc.
Ribo-Seq
Ribosome profiling, or Ribo-Seq (also named Ribosome foot printing), is an adaptation of a technique developed by Joan Steitz and Marilyn Kozak almost 50 years ago that Nicholas Ingolia and Jonathan Weissman adapted to work with next generation sequencing that uses specialized messenger RNA (mRNA) sequencing to determine which mRNAs are being actively translated.
Principle
Ribosome footprint profiling. (doi:10.1038/nrg3645)
Sample Requirement and Sequencing Strategy
Sample Type
Amount
Sequencing Strategy
Recommended Data Amount
RPF
(Ribosome-Protected Fragment)
Amount ≥ 600 ng; concentration ≥ 100 ng/μL volume ≥ 6ul;
no observable color
SE50
50 M reads
Analysis Content
Ribo-Seq Standard Analysis
Remarks
Removal of adapters, contaminated and low-quality reads
/
Composition and quality assessment of data output statistics and sequencing data
/
Read length statistics for screening RPFs with lengths between 26 and 32 nt for subsequent analysis
/
Reference sequence alignment analysis
Requires reference genome
RPF expression analysis
/
Inter-sample correlation analysis (≥ 2 samples)
/
Gene classification
/
- Note: We don’t have English report, please contact APM in advance if you need English report.
For advanced analysis, sales/technical support should consult the product manager first. Advanced analysis includes but not limited to following contents.
Ribo-seq Advanced Analysis
Remarks
TE analysis
(Combining with RNA-Seq data)
Differential TE expression analysis
Need to do RNA-Seq analysis at the same time
Differential TE gene clustering analysis
GO enrichment analysis of TE gene with significant difference
KEGG enrichment analysis of TE gene with significant difference
/
uORF analysis
uORF length analysis
/
uORF sequence analysis
/
## FAQ
- What is RPF and how to get RPF?
- A: RPF means ribosome footprints with ~30 nt in length.
Experimental principle: Cells or tissues were treated with translation inhibitors. First, free mRNA was digested by nuclease, and then ribosomal mRNA complexes were enriched to obtain RPFs. After rRNA was removed and purified with PAGE gel, the target RNA fragment was obtained.
We suggest using MicroSpin S-400 columns to get RPFs.
- Can we accept the lysis product? How to lysis the tissue or cells?
- A: Based on our experience, the lysis product does not perform as well as RPFs or cell/tissue samples. Therefore, if a customer cannot provide tissues or cells, we recommend they provide RPFs instead.
- What is the process of Ribo-Seq library preparation?
- A: The lysis product of animals and plants were first digested by RNase I to separate ribosome bounding RNA and free RNA. Microspin S-400 column was used to enrich ribosome mRNA complex to obtain RPFs. After rRNA was removed and purified with PAGE gel, the target RNA fragment was obtained. End repair, A tailing, and directly add 5 'and 3' adapters at both ends. Then the cDNA was synthesized by reverse transcription, enriched by PCR, and the target fragment was screened by PAGE gel to obtain the library containing the target fragment. After the library QC is qualified, sequencing will be proceeded
- Can a customer extract the RNA from the lysis product before Ribo-Seq?
- A: CAN NOT. For Ribo-seq, the transient state of ribosome translation needs to be kept, and RNA extraction will disrupt the transient state and mess up different kinds of RNA. If RNA-Seq and Ribo-Seq analysis are required at the same time, two copies of the same sample need to be prepared.
If a customer wants to do Ribo-Seq and RNA-Seq for the same sample, how should sample be delivered?
- A: Sample should be divided into 2 parts:
-Ribo-Seq: intact tissue/cell sample or RPFsample.
-mRNA-seq: total RNA or a separate tissue/cell sample for total RNA extraction .
Does Ribo-Seq analysis need reference genome?
- A: Reference genome and corresponding annotations are required.
In Ribo-Seq, the proportion of ribosomal RNA (rRNA) among samples is not uniform. What is the reason for this situation?
- A: Ribo-seq enriches ribosomal complexes and their protected mRNA fragments and then enriches the ribosomal-protected fragments in the products. The concentration and total amount of rRNA are significantly higher than that of RNA-seq. Moreover, due to the influence of sample quality and species, the efficiency of removing rRNA by experimental method may be unstable, so the proportion of rRNA is not promised in the project delivery data. In the analysis, we will compare the filtered clean reads to the ribosomes of the species, remove the reads of rRNA and the retained data will be used for subsequent analysis.
Whole Genome Bisulfite Sequencing (WGBS)
Principle
5mC (DNA methylation at the C5 position of cytosine) plays a crucial role in gene expression and chromatin remodeling. Perturbations in methylation patterns are implicated in the development of cancer, neurodegenerative diseases and neurological disorders. It’s critical to position methylated bases (the methylome) to understand gene expression and other processes subject to epigenetic regulation. Methylome analysis is an increasingly valuable research approach with a range of applications, including studies on gene regulation, stem cell differentiation, embryogenesis, aging, cancer and other diseases, phenotypic diversity, and evolution in plants and animals.
Exemplary DNA double strand with methylated (red) and unmethylated (blue) CpG-site (cytosine-phosphate-guanine-dinucleotide) before and after bisulfite application and polymerase chain reaction (PCR). (https://doi.org/10.3390/epigenomes2040021)
Sample Requirement
Sample Type
Amount
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
Genomic DNA
≥ 0.2 μg
≥ 20 μL
≥ 5 ng/μL
0 < OD260/230 < 3
No degradation, no contamination
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Sequencing Depth
Turnaround Time (≤ 20 samples)
WOBI
WBI
Whole Genome Bisulfite Sequencing (WGBS) Library
PE150
≥ 30X
25 working days
43 working days
Analysis Content
Standard Analysis
Software
Trimming of raw data (filtering reads containing adapter or with low quality)
fastp
Data quality control (Q20, Q30, error rate distribution, GC distribution, total bases)
fastqc
Mapping onto reference genome (mapping rate, duplication rate, sequencing depth, reads coverage)
Bismark
mCs detection, methylation level calculation
Methylation level and frequency distribution in different sequence context (CG, CHG, CHH)
Methylation level and frequency distribution in different chromosomes
Methylation level and frequency distribution in different functional elements (promoter, 5'UTR, exon, intron, 3'UTR)
Bismark
Diferentially methylated regions (DMRs) detection and annotation
DSS
Function enrichment (Gene Ontology and KEGG Pathway) of DMR-associated genes.
GOSeq, topGO, Bioconductor; KOBAS
Visualization of BS-seq data
/
For advanced analysis, sales/technical support should consult the product manager first. Advanced analysis includes but not limited to following contents.
mRNA-WGBS Association Analysis
Software
Overall association Circos diagram
/
Methylation levels of gene body and its upstream and downstream at different expression levels
/
Gene expression levels at different methylation levels
/
DMR related gene expression and methylation modification
/
Correlation between methylation level and expression level
/
Association analysis of DMR related genes and differentially expressed genes (Venn, heatmap, line chart)
/
GO enrichment (overlapping gene)
GOSeq, topGO;Bioconductor; KOBAS
KEGG enrichment (overlapping gene)
GO enrichment (target promoter gene)
KEGG enrichment (target promoter gene)
Motif analysis (overlapping gene)
homer
Motif analysis (target promoter gene)
## FAQ
- What is the species limitation for analysis?
- A: Only species (human/plant/animal) with reference genomes are accepted. Special samples CANNOT be used for methylation sequencing:
Methyl-free species: Saccharomyces, Caenorhabditis elegans, Drosophila;
Methylated organelle: chloroplast, mitochondria;
Prokaryote
If client wants 15-20x data considering the limitation budget, can we accept data analysis?
- A: For WGBS sequencing, we recommend at least 30x for analysis, considering raw data to clean data and mapping rate, all of them may impact the final data used for final analysis. If client only orders 15-20x, we are not sure about the analysis result can meet client's requirement, for example, maybe the methylation site is quite low or even can't find some sites. From software and technical perspective, we can still accept 15-20x data with unknown analysis result.
- Can we offer the WGBS service for cfDNA?
- A: Our lab has experience processing cfDNA, and we recommend a minimum input of 30 ng per sample. However, since this amount is below our standard requirement, the sample will be identified as FAIL during sample QC, and library preparation will proceed with risks.
Optional solution-EM-Seq: We recommend our EM-Seq service as a superior alternative. It uses an enzymatic conversion (unmethylated C to U), which is gentler than bisulfite treatment and enables library prep from lower DNA inputs. We offer the standard EM-Seq service for both gDNA and cfDNA. Please refer to the following sample requirement.
Sample Type
Amount
Volume
Concentration
Purity (NanoDropTM/Agarose gel)
Genomic DNA
≥ 30 ng
≥ 30 μL
≥ 1 ng/μL
0 < OD260/230 < 3
No degradation, no contamination Fragments should be above 3000bp
cfDNA
≥ 20 ng
≥ 20 μL
≥ 1 ng/μL
Main peak at 170 bp or its integer multiples
Reduced Representation Bisulfite Sequencing (RRBS)
Reduced-Representation Bisulfite Genome Sequencing (RRBS) is an accurate, efficient and economical method for DNA methylation research. Enrichment of promoter and CpG island regions by enzymatic cleavage (MspI), combined with Bisulfite sequencing, provides high resolution DNA methylation detection.
Principle
Reduced representation bisulfite sequencing. (Modified by doi.org/10.1093/nar/gki901)
Sample Requirement
Sample Type
Recommended Amount
Volume
Concentration
Purity (NanoDropTM/Agarose Gel)
Genomic DNA
≥ 1 μg
≥ 20 μL
≥ 25 ng/μL
0 < OD260/230 < 3
No degradation, no contamination
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data Amount
Turnaround Time (≤ 20 samples)
WOBI
WBI
Reduced Representation Bisulfite Sequencing (RRBS)
Library
PE150
10 Gb
25 working days
43 working days
Analysis Content
Standard Analysis
Software
Trimming of raw data (filtering reads containing adapter or with low quality)
fastp
Data quality control (Q20, Q30, error rate distribution, GC distribution, total bases)
fastqc
MspI cutting efficiency
/
Mapping onto reference genome (mapping rate, sequencing depth, reads coverage). Sequencing depth and reads coverage on genetic regions
Bismark
mCs detection, methylation level calculation
Methylation level and frequency distribution in CG sequence context
Methylation level and frequency distribution in different functional elements (promoter, 5'UTR, exon, intron, 3'UTR)
Bismark
Differentially methylated regions (DMRs), Differentially Methylated Promoter (DMPs) detection and annotation
DSS
Function enrichment (Gene Ontology and KEGG Pathway) of DMR-associated genes and DMP-associated genes
GOSeq, topGO; Bioconductor; KOBAS
Visualization of data
/
Novogene Product Manual
PacBio Sequencing
AMEA 2025 08
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
11 PacBio Sequencing AMEA Product Manual-2025 V3.1
Revision Number
2025 V3.1
Issue Date
August 21, 2025
Prepared by
Liu Rui
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V2.0
Overall renewed for this version.
Overall proofreads glossary, service name and service overview.
Update sample requirements, turnaround time and products information of all types of service.
Liang Yan Liu Rui
May 22, 2023
2023 V3.0
Page 11: Add extra note regarding HiFi library sample amount-9ug.
Page 12: Increase recommended sequencing depth of de novo assembly to 60X.
Liang Yan Liu Rui
June 08, 2023
Page 20, 28, 40: Add PacBio official extraction reference under HMW extraction FAQ.
2024 V1.0
Page 10: Service update.
Page 12, 27: Update sample requirements of HiFi library.
Page 20-FAQ 1: Complement details of kinetics data and de novo seq. Page 23-FAQ 7, 24-FAQ 8Q: Add genome survey related information. Page 25-FAQ 10: Revio experience data update.
Page 26-FAQ 13, 31-FAQ 3, 35-FAQ 2: Update PCR products sequencing. Page 27: Sequencing strategy and turnaround time update.
Page 38: Iso-Seq updates.
Page 44-FAQ 4: Software updates.
Liang Yan Liu Rui
January 22, 2024
2024 V2.0
Page 23-FAQ 09~11: Update the guaranteed data output information and conditions for Revio HiFi sequencing
Liang Yan Liu Rui
March 11, 2024
2024 V3.0
Page 9: Add Kinnex related information in glossary. Page 10: Update platform information.
Page 17~18: Add information about additional services, including data output promise service and low-input service.
Page 34: Add Kinnex RNA sample requirements.
Overall updates of sequencing strategy, data delivery, analysis content and FAQ for all services.
Liang Yan Liu Rui
August 30, 2024
2024 V4.0
Page 18: Update on data output promise service
Page 27, 32, 35: Update on PCR product sample requirement Page 37~47: Overall updates of Iso-Seq service
Liang Yan Liu Rui
November 28, 2024
2025 V1.0
Page 18: Revio data output promise service Page 46: Kit updates
Liang Yan Liu Rui
April 09, 2025
2025 V2.0
Page 19: Update Revio data output promise service Page 21: Update methylation information
Overall updates:
-Remove CLR related products
-Relocate PacBio metagenomics to the metagenomics product manual and full-length 16S sequencing to the amplicon product manual.
-Microbial HiFi sequencing
-Add “Guide to Making a Quotation”
Liang Yan Liu Rui
May 30, 2025
2025 V3.0
Page 13: Sample requirement updates
Page 19: Update Revio data output promise service
Liang Yan Liu Rui
June 30, 2025
2025 V3.1
Page 19: Update Revio data output promise service
Update information related to Sequel II/IIe platform and premade library.
Liang Yan Liu Rui
August 21, 2025
Content
PacBio Sequencing Glossary7
PacBio Service Overview11
PacBio DNA Sequencing (Human/Plant/Animal)13
## Sample Requirements13
Sequencing Strategy and Turnaround Time13
Analysis Contents14
Data Delivery16
Additional services18
## FAQ22
PacBio DNA Sequencing (Bacteria/Fungi)30
## Sample Requirements30
Sequencing Strategy and Turnaround Time30
Guide to Making a Quotation31
Analysis Contents32
Data Delivery34
## FAQ35
PacBio Full-Length RNA Sequencing37
## Sample Requirements37
Sequencing Strategy and Turnaround Time37
Guide to Making a Quotation38
Analysis Contents38
Data Delivery41
## FAQ41
General FAQ46
PacBio Sequencing Glossary
SMRT Cells 25M: SMRT Cells used with the Revio instrument, containing 25 million zero mode waveguides, and supporting movie collection time of 24 hours.
SMRT Cells 8M: SMRT Cells used with the Sequel II/ IIe instrument, containing eight million zero mode waveguides, and supporting movie collection times up to 30 hours. The Sequel II/IIe platform has been discontinued, with all projects now using the Revio platform for sequencing.
Movie time: The time specified for collecting data from a SMRT Cell.
SMRTbell® template: A double-stranded DNA template capped by hairpin adapters (i.e., SMRTbell adapters) at both ends. A SMRTbell template is topologically circular and structurally linear and is the library format created by the DNA Template Prep Kit.
Circular Consensus Sequencing (CCS) Read: Sequencing performed on a circular template in which a subread was generated during a sequencing pass around the template. These reads are aligned to each other to generate a single high-accuracy consensus read. CCS analysis to generate consensus reads requires CCS data with at least two full pass subreads.
HiFi reads (High-fidelity long reads): HiFi reads are produced using circular consensus sequencing (CCS) mode on PacBio long-read systems. HiFi reads provide base-level resolution with an average of 99.9% read accuracy.
Polymerase read: A sequence of nucleotides incorporated by the DNA polymerase while reading a template, such as a circular SMRTbell template. They can include sequences from adapters and from one or multiple passes around a circular template, which includes the insert of interest. Polymerase reads are most useful for quality control of the instrument run. Polymerase read metrics primarily reflect movie length and other run parameters rather than insert size distribution. Polymerase reads are trimmed to include only the high-quality region. Note: Sample quality is a major factor in polymerase read metrics.
Subread: Each polymerase read is partitioned to form one or more subreads, which contain sequence from a single pass of a polymerase on a single strand of an insert within a SMRTbell template and no adapter sequences. The subreads contain the full set of quality values and kinetic measurements. The new PacBio sequencing system, Revio, does not provide intermediate subread data, but directly delivers the final HiFi data.
Insert size: The length of the double-stranded nucleic acid fragment in a SMRTbell template, excluding the hairpin adapters.
SMRT® Link: Web-based end-to-end workflow manager. It includes software applications for setting up samples, designing and monitoring sequencing runs, and analyzing and managing sequence data.
KinnexTM kit: The Kinnex kit utilizes the MAS-Seq method, which concatenates smaller amplicons into larger fragment libraries for throughput increase. The Kinnex application kits include the Kinnex full-length RNA kit, Kinnex single-cell RNA kit, and Kinnex 16S rRNA kit. Currently, we can
offer the sequencing using Kinnex full-length RNA kit and Kinnex 16S rRNA kit. For Kinnex single-cell RNA sequencing, please check with APM team case by case.
KinnexTM full-length RNA kit: With the Kinnex full-length RNA kit, 8 cDNAs will be concatenated together to form a single library, resulting in an 8X increase in throughput compared to regular Iso-Seq. When combined with the use of the PacBio Revio system, there will be 16 times more data at a lower cost than regular Iso-Seq on the Sequel IIe platform.
## PacBio Service Overview
Service Type
Application
Library Type
Sequencer
Default Data Delivery
- Can we provide BI analysis*
Remark
DNA service
Human/ Plant/ Animal Re-Seq
HiFi library
Revio
hifi_reads.bam
Y
**
***
Human/ Plant/ Animal
De Novo Seq
HiFi library
Revio
hifi_reads.bam
Y
Metagenomics
HiFi library
Revio
hifi_reads.bam
Y, need evaluation
Please refer to metagenomic product manual
Bacteria Re-seq
HiFi library
Revio
hifi_reads.bam
N
Bacteria Complete Map
HiFi library
Revio
Hifi_reads.bam
Y
Fungi Re-Seq
HiFi library
Revio
hifi_reads.bam
N
Fungi Fine Map
HiFi library
Revio
hifi_reads.bam
Y
Full-length 16S Sequencing
Kinnex full-length 16S library
Revio
fastq
Y
Please refer to amplicon product manual
RNA service
Eukaryotic RNA Sequencing
Kinnex full-length RNA library
Revio
hifi_reads.bam
Y
- Note:
*For the analysis details, please refer to analysis contents or demo report. All other customized analyses that are not in the list, please check with APM team case by case.
**Human/ Plant/ Animal HiFi library can be sequenced in Singapore lab using Revio platform and we can only deliver hifi_reads.bam
***For Human/Plant/ Animal DNA HiFi sequencing, 5mC (in CpG Motifs) is included in hifi_reads.bam and will release to customer automatically.
PacBio DNA Sequencing (Human/Plant/Animal)
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity
PacBio DNA HiFi library
HMW* Genomic DNA(Human/Plant/Animal)
≥ 3.5μg** (Additional 3μg per sample per Cell)
≥ 85 μL
≥ 40 ng/μL
OD260/280=1.75~2.0 OD260/230=1.5~2.6 NC/QC***=1.00~2.20
Fragments should be ≥ 30K
- Note:
*HMW: High Molecular Weight
**3.5μg: 3.5μg is the sample amount for one time library preparation. One library can only be used for one SMRT Cell. If customers want to sequence 2 or more cells, an additional 3μg per sample per Cell is needed for additional libraries. Please also charge the extra library preparation cost.
***NC/QC: NanoDrop concentration/Qubit concentration Recommended suspension buffer: EB.
Sequencing Strategy and Turnaround Time
Application
Library Type
Recommended Sequencing Depth*
Turnaround Time (≤ 10 Cells)
WOBI
WBI**
Human Re-seq
HiFi library
≥ 20X HiFi reads (recommend 25x and above)
22 working days
32 working days
Plant & Animal Re-seq
HiFi library
≥ 20X HiFi reads (recommend 25x and above)
22 working days
37 working days
Human/Plant/Animal De Novo Seq
HiFi library
50X illumina data+≥ 60X HiFi reads (Diploid)***
30 working days
Case by case
- Note:
*Recommended Sequencing Depth: The minimum order of HiFi sequencing is one Cell. If the required data amount is lower than the output of one cell, please still order one cell. To reduce the costs, customers can appropriately pool their samples within one Cell. For the expected data output per Cell and sample pooling recommendations, please refer to FAQ 9, FAQ 10.
**WBI: The WBI turnaround time is calculated according to standard analysis. For advanced analysis, there will be an additional 5-7 working days.
***50X illumina data+≥60X HiFi reads (Diploid): The 50X illumina data is for genome survey and it's highly recommend using the same sample as the one for PacBio HiFi sequencing. 60X HiFi data is typically for contig-level assembly of Diploid species. To achieve chromosome-level or T2T-level genome assembly, a combination of Hi-C and Nanopore ultra-long DNA sequencing data is required. For more details, please check with APM team.
Analysis Contents
Human/ Plant/ Animal Re-seq-Standard Analysis
Software
Data quality control: raw data processing and data statistics
SMRTlink
Alignment with reference and statistics
Minimap2
SV calling, annotation and statistics
Sniffles, ANNOVAR
Circos Plot
Circos
Human/ Plant/ Animal Re-seq-Advanced Analysis
Software
Data quality control: raw data processing and data statistics
SMRTlink
Alignment with reference and statistics
Minimap2
SV calling, annotation and statistics
Sniffles, ANNOVAR
SNP and InDel calling, annotation and statistics
DeepVariant, ANNOVAR
Circos Plot
Circos
Human/ Plant/ Animal Re-seq-Customized Analysis
Software
CNV calling and statistics
CNVkit
STR calling and statistics (only for human re-seq)
RepeatHMM
Human/ Plant/ Animal De Novo Seq-Genome Assembly*& Annotation**
Note
Software
Genome assembly and assessment
The fasta file will be delivered to customers.
Hifiasm
Repeat sequence annotation
Gff file, CDS fasta file and protein sequence will be delivered to customers.
RNA-seq data is required for customers opting for the annotation service. It is highly recommended to use samples from the same individual with genome assembly. Customers can select 5~6 samples from different tissues or developmental stages with >6Gb data/
sample.
Repeatmasker,
RepeatModeler
Gene structure annotation
August, GlimmerHMM,
SNAP, EVM
Gene function annotation
Non-coding RNA annotation
INFERNAL
*Assembly: It is recommended to conduct a genome survey using Illumina short-read data before initiating the analysis. The sample used for the genome survey should be the same one as that used for the genome assembly. Customers can simply set aside a portion of HMW DNA for genome survey. For chromosome or T2T level assembly, please check details with APM team.
**Annotation: The annotation service is optional but can only be performed after we have obtained the genome assembly. If it is difficult to obtain RNA-seq samples based on our recommendations, it's also acceptable to use samples from different individuals or even data from public databases. However, individual differences may complicate the annotation process and impact the analysis results.
Data Delivery
Data release structure for WOBI projects: HiFi reads are provided (hifi_reads.bam). Data release structure for WBI projects:
-Standard analysis- (HiFi reads as default)- SV detection
-Advanced analysis- (HiFi reads as default)- SV, SNP and InDel detection
Additional services
Revio data output promise service
The Revio data output promise service is available for human/ plant/ animal Revio HiFi genome sequencing; however, actual data output may vary depending on sample species. For more details, please refer to the table and conditions below.
Species overview:
Species
Data Size/ Cell
Typical species
Human
130Gb HiFi reads
General animals
120Gb HiFi reads
Mammals (mouse, rat, pig, horse, cow, sheep, goat, etc.), birds
General plants
120Gb HiFi reads
Crops (HMW DNA from leaves of Arabidopsis, cotton, Nicotiana tabacum, peanut, Sorghum bicolor, maize, wheat, barley)
Poultry
90Gb HiFi reads
Phasianus, Gallus, Anas
Others
80Gb HiFi reads
The species not indicated in the list.
PCR product and aquatic species sequencing excluded.
Aquatic species
60Gb HiFi reads
Fish
Detailed species list (If you're uncertain about the amount of data we can guarantee, please refer to the list): https://doc.weixin.qq.com/sheet/e3_AHIAhAYTAN0QscFzWPOSOGDJC6ynK?scode=AJgAAQcaAAwI9a1wbOAHIAhAYTAN0&tab=000002 (Special notice: The amount of data we can guarantee is based on the genus type. Sheet1 and sheet2 are general plants and animals. Sheet3 is the non-common genus/ species with special remarks. For the genus not included in the list (excluding aquatic species, which are only guaranteed 60Gb), we can only treat it as non-common samples and only promise 80Gb. Brassica napus is another special species. Based on our previous
experience, many projects involving Brassica napus have not yielded any data. Therefore, we do not recommend accepting or guaranteeing data output for Brassica napus. For important projects, please check with the APM team in advance.)
The data output promise service is applicable when the project meets the following conditions:
-This service is applicable only to PASS samples (excluding human low-input samples). If customers pool different samples into one Cell, all samples should be PASS. Additionally, we can only guarantee the data output when < 4 samples are pooled in the same Cell, and they are of the same species.
-The starting material should be gDNA intended for HiFi DNA sequencing on the Revio platform. If the samples are PCR products, we don’t promise any data output.
- Note: Currently, the guaranteed data volume is based on the genus type, as congeneric species typically exhibit similar characteristics. However, since we lack data for all species within a given genus, certain exceptional cases may fail to achieve the promised data values. If the combined yield from the initial sequencing round and subsequent top-up falls below 60% of the guaranteed amount, the shortfall will be attributed to species-specific factors, complimentary top-up sequencing will not be provided.
Human low-input HiFi library preparation service (paid service)
Library TypeSample TypeAmountVolumeConcentrationPurityLibrary TypeSample TypeAmountVolumeConcentrationPurityThe human low-input HiFi library preparation service is now available. If samples meet the requirements below, the low-input library preparation can be attempted.
Library Type
Sample Type
Amount
Volume
Concentration
Purity
Library Type
Sample Type
Amount
Volume
Concentration
Purity
PacBio DNA Human Low-Input HiFi library
HMW* Genomic DNA (Human)
≥1.2 μg**
≥ 40 μL
≥30 ng/μL
OD260/280=1.75~2.0 OD260/230=1.5~2.6 NC/QC***=0.95~3.00
Fragments should be ≥ 30K
*HMW: High Molecular Weight
**≥1.2 μg: 1.2μg is only enough for one time library preparation. One library can only be used for one SMRT Cell.
***NC/QC: NanoDrop concentration/Qubit concentration
Library preparation method: Optimized pipeline using SMRTbell® Prep Kit 3.0.
Notice: Typically, achieving sufficient data output and the desired read length requires an adequate amount of input DNA, along with potential size selection to ensure the HiFi library falls within the standard 15Kb-20Kb range. However, for low-input samples, some of these parameters must be adjusted to ensure that the concentration or quantity of the library is sufficient for sequencing. Thus, the final data output or N50 read length might not be as good as the standard library preparation pipeline and we’re unable to guarantee the data output per Cell.
Key advantages: In contrast to other low-input library preparation methods, our low-input method does not involve any additional PCR amplification steps. For example, the PacBio official low-input library preparation kit, increases the input DNA amount through PCR amplification. This process can introduce base bias and the presence of PCR chimeras. The valuable methylation information will be lost during PCR amplification as well. Instead, we optimize the standard library preparation pipeline using the SMRTbell® Prep Kit 3.0, ensuring data quality while avoiding PCR-related issues.
Special Offer on hWGS (2025 Q3-Q4): Get 10 Human Genomes (20X) for Under $10K!
Currently, we are running a 20X hWGS price promotion in AMEA (excluding Japan). This promotion applies to individual hWGS samples, providing
20X coverage/sample (60Gb HiFi data). Unlike our previous PacBio projects that required whole cell orders, this promotion allows direct provision of 60Gb HiFi data for each individual sample.
Sample requirement: Same as the sample requirement for standard PacBio DNA HiFi library. Please refer to Page 13-Sample Requirement.
Guaranteed data amount: 60Gb HiFi data/ sample, which only applies for PASS samples.
Low-input library preparation is excluded.
Guide to Making a Quotation: Please pay attention to the following items when making a quotation: Process Type, PacBio Revio (HiFi reads); Data Size, 60. The rest of the items can be selected as usual. Regarding the sequencing cost, please use the promotion package price minus library preparation cost (sales or director level).
- Note:
-Purchase Order (PO) and samples must be received by Novogene on or before 30 November 2025. A minimum project value of $3,000 USD (PO) is required for eligibility. For more detailed terms and conditions, please refer to our promotion page: https://web.novogene.com/AMEA-2025-Q2-hifireads?_gl=1*10ok3f3*_gcl_au*MTQ2MDgyNzQ2My4xNzQyMzU0NDEw.
-We are also evaluating the possibility of launching 20X hWGS as a standard service, primarily due to the increasing throughput of PacBio platforms. For regions not included in the promotion, please contact the APM team for any related inquiries.
## FAQ
QuestionsPossible Answers& SolutionsRemarkQ1: Have you done PacBio sequencing before?Yes, to A1. No, to Q2A1: Refer to previous project information, but please notice technology update.Q2: What is your research purpose? Does the species you study have a reference genome?Yes, to A2 No, to A3A2: If a customer looks for re-seq, we recommend 25x HiFi reads or above. If not, please check with APM team.A3: If a customer wants to perform de novo assembly and annotation, please let customers fill in ‘Lead information form for de novo genome sequencing’* or directly check required information with customers. For more details, please refer to FAQ-7Q.Q3: Do you need other information like methylation or kinetics information?Methylation information, to Q4 Kinetics information: A4A4: On the PacBio Revio system, kinetics information can be separately set. If requested by the client, we can provide HiFi data along with kinetics information to customers.Please add a remark and inform PM team in advance toDuring quotation, please choosecorrect data delivery type and remark the requirement of kineticsinformation in Quotation- Note-QuestionsPossible Answers& SolutionsRemarkQ1: Have you done PacBio sequencing before?Yes, to A1. No, to Q2A1: Refer to previous project information, but please notice technology update.Q2: What is your research purpose? Does the species you study have a reference genome?Yes, to A2 No, to A3A2: If a customer looks for re-seq, we recommend 25x HiFi reads or above. If not, please check with APM team.A3: If a customer wants to perform de novo assembly and annotation, please let customers fill in ‘Lead information form for de novo genome sequencing’* or directly check required information with customers. For more details, please refer to FAQ-7Q.Q3: Do you need other information like methylation or kinetics information?Methylation information, to Q4 Kinetics information: A4A4: On the PacBio Revio system, kinetics information can be separately set. If requested by the client, we can provide HiFi data along with kinetics information to customers.Please add a remark and inform PM team in advance toDuring quotation, please choosecorrect data delivery type and remark the requirement of kineticsinformation in Quotation- Note-What questions can I ask when receiving a Human/ Plant/ Animal genome sequencing inquiry with PacBio platform? A: Here are some general questions you can ask when you have a new inquiry.
Questions
Possible Answers& Solutions
Remark
Q1: Have you done PacBio sequencing before?
Yes, to A1. No, to Q2
A1: Refer to previous project information, but please notice technology update.
Q2: What is your research purpose? Does the species you study have a reference genome?
Yes, to A2 No, to A3
A2: If a customer looks for re-seq, we recommend 25x HiFi reads or above. If not, please check with APM team.
A3: If a customer wants to perform de novo assembly and annotation, please let customers fill in ‘Lead information form for de novo genome sequencing’* or directly check required information with customers. For more details, please refer to FAQ-7Q.
Q3: Do you need other information like methylation or kinetics information?
Methylation information, to Q4 Kinetics information: A4
A4: On the PacBio Revio system, kinetics information can be separately set. If requested by the client, we can provide HiFi data along with kinetics information to customers.
Please add a remark and inform PM team in advance to
During quotation, please choose
correct data delivery type and remark the requirement of kinetics
information in Quotation- Note-
Questions
Possible Answers& Solutions
Remark
Q1: Have you done PacBio sequencing before?
Yes, to A1. No, to Q2
A1: Refer to previous project information, but please notice technology update.
Q2: What is your research purpose? Does the species you study have a reference genome?
Yes, to A2 No, to A3
A2: If a customer looks for re-seq, we recommend 25x HiFi reads or above. If not, please check with APM team.
A3: If a customer wants to perform de novo assembly and annotation, please let customers fill in ‘Lead information form for de novo genome sequencing’* or directly check required information with customers. For more details, please refer to FAQ-7Q.
Q3: Do you need other information like methylation or kinetics information?
Methylation information, to Q4 Kinetics information: A4
A4: On the PacBio Revio system, kinetics information can be separately set. If requested by the client, we can provide HiFi data along with kinetics information to customers.
Please add a remark and inform PM team in advance to
During quotation, please choose
correct data delivery type and remark the requirement of kinetics
information in Quotation- Note-
include all base kinetics information.
Description. Except the extra data release cost, there is no additional cost for kinetics information.
- Note: Adding kinetics information can increase the amount of storage used by the output BAM files by up to 5 times.
Q4：What species is it?
Human and other vertebrates, to A5 Other eukaryotes including plants, to A6
A5: Methylation in Human and other vertebrates mainly occurs in CpG dinucleotides, where both cytosines on the strands are usually methylated. The on-instrument HiFi sequencing detects 5mC in CpG context, and this methylation information is stored in the BAM file using ML/MM tag formatting and release to customers by default. For customers requiring in-depth methylation analysis, we recommend releasing the kinetics data alongside standard
sequencing data.
A6: DNA methylation in plants and other organisms mainly occurs in three different sequence contexts: CG (or CpG), CHG, or CHH (where H corresponds to A, T, or C). PacBio HiFi sequencing currently supports the accurate 5mC detection in CpG sites. For 5mC detection in non-CpG
sites, please release kinetics data (refer to A4).
- Note:
Lead information form for de novo genome sequencing*: Please refer to WeDrive-AMEA documents- APM team-Product related supporting documents-De Novo.
Data format requiredLibrary TypeDefault?Data release size per Cell *Data release methodHDD sizeHiFi dataHiFi libraryYes50-70GbCloud/ HDDIf client requires kinetics information, HDD is highly recommended as theData format requiredLibrary TypeDefault?Data release size per Cell *Data release methodHDD sizeHiFi dataHiFi libraryYes50-70GbCloud/ HDDIf client requires kinetics information, HDD is highly recommended as theHow to calculate data release size and choose appropriate data delivery method? A:
Data format required
Library Type
Default?
Data release size per Cell *
Data release method
HDD size
HiFi data
HiFi library
Yes
50-70Gb
Cloud/ HDD
If client requires kinetics information, HDD is highly recommended as the
Data format required
Library Type
Default?
Data release size per Cell *
Data release method
HDD size
HiFi data
HiFi library
Yes
50-70Gb
Cloud/ HDD
If client requires kinetics information, HDD is highly recommended as the
data size is quite huge (~5X).
- Note:
Data release size per Cell *: For data release calculation only, it does not equal to the real data output.
- Can we perform HMW DNA extraction for human, plant or animal tissues?
- A: Sorry, currently we can’t provide HMW DNA extraction. Here are some recommended kits for help: Circulomics / Qiagen Gentra Puregene / Qiagen MagAttract HMW DNA extraction kits. PacBio also provides official recommendations. Here is the link: https://extractdnaforpacbio.com.
Which kit do we use for HiFi library prep?
- A: Tianjin/ Singapore lab: SMRTbell prep kit 3.0.
- How to choose HiFi library or CLR library for human, plant and animal sequencing?
- A: The CLR library is no longer available. HiFi sequencing has become the primary technology for PacBio long-read sequencing, offering significantly higher data accuracy and better analysis results compared to CLR libraries. For all inquiries, we strongly recommend using HiFi sequencing (refer to below picture).
If a client has an exogenous DNA insertion in a plant or animal genome and wants to identify the insertion loci, what is our solution?
- A: We recommend using PacBio HiFi library to sequence the genome at a depth of at least 20x. The client needs to provide both the reference genome and the sequence of DNA insertion. Our analysis workflow integrates DNA insertion with the reference genome to create a new composite reference genome. This modified reference is then used to call structural variations (SVs), from which insertion events are further filtered. The target DNA can be identified by performing a BLAST alignment with these filtered insertions. However, insertion number and insertion site might not be accurate. The customer needs to further verify based on their specific research purpose. Additionally, germline SV variation may prevent the identification of all insertions.
If a customer wants to perform de novo assembly and annotation, what information we need to ask and what kind of analysis can we provide?
- A: For WOBI projects, the process is relatively straightforward. We can first check the species information and determine the level of genome assembly required by the customer. Check the sequencing strategy listed in “2. Sequencing Strategy and Turnaround Time”. For higher-level assembly, please check details with APM team.
- Note: Plant and Animal De novo Sequencing (PacBio) in SFDC is only for WBI projects. For WOBI projects, please select “Plant and Animal Whole Genome Sequencing (PacBio) (WOBI)”, “Plant and Animal Eukaryotic mRNA (WOBI)” and “Hi-C (WOBI)”.
For WBI project, here is the general workflow:
Pre-sale evaluation: Please let customers complete our ‘Lead information form for de novo genome sequencing’ or provide relevant information. The basic information required for evaluation is listed in Section 1, including species name, genome size, and ploidy. If customers require Hi-C data for chromosomal-level assembly, they should also specify the chromosome number. Customers can also specify their special requirements in Section 2, like the sequencing preferences, desired assembly level, and any specific requirements for the bioinformatics analysis.
The APM team provides draft analysis costs based on the information submitted.
Genome survey: Based on the genome survey results, customers can decide whether to proceed with the subsequent analysis. In addition, if the survey results differ significantly from the initial information provided, we may also adjust the quotation.
Proceed de novo assembly& annotation analysis.
- Note: One individual is recommended for one genome assembly. If obtaining sufficient HMW DNA from a single individual is challenging, the assembly can still be performed; however, the results may be less accurate, and the genome size may be larger.
If a customer insist that they don’t want to perform genome survey or they already do it by themselves, can we skip this step and directly perform
de novo sequencing and analysis for them?
- A: Before making the decision, please check details with the customer first. Genome survey is used to check basic genome information, including genome size, GC content, heterozygous rate, repeat rate and contamination. This information is essential to estimate the result of de novo assembly and annotation. Particularly when the estimated genome size and other customer-provided information are inaccurate, conducting a genome survey helps identify potential risks beforehand for both customers and us. In the case where customers already do it themselves, but a separate sample is sent to us for de novo sequencing, we still recommend a genome survey. This is because microbial or other species contamination vary among different extracts and these non-target genomes will affect final analysis result. If a customer insist on skipping genome survey, the analysis can be carried out while please inform the risks with customers.
- What is the expected data output per Cell for HiFi library, Revio system? Can we guarantee the data output for PacBio Revio sequencing?
- A: For the expected data output per Revio Cell and data guarantee information, please refer to “5 Additional services- Data output promise service”.
- Can we accommodate the request of pooling samples into 1 Cell and guarantee data output for PacBio Revio sequencing?
- A: As we offer PacBio HiFi sequencing on a per-cell basis, customers are limited to pooling their own samples within each Cell. We highly recommend pooling samples from the same species, with a maximum of three samples per Cell. While it is technically possible to pool more samples or include different species within a single Cell, we do not recommend this approach. If customers choose to proceed with this option, they should be made aware of the potential risks, such as lower data output per Cell or uneven data distribution among samples. The data guarantee service is applicable when the project meets the following conditions:
≤4 samples are pooled in one Cell.
All samples are of the same species.
All samples pass sample QC.
The guaranteed data applies to the entire Cell, rather than each individual sample.
If a client wants to send us premade library for PacBio sequencing, what question should you ask before quotation?
- A: We need to check the species, library prep kit, library type (Kinnex Iso-Seq/bulk RNA library, standard DNA HiFi library, Kinnex scRNA library or other types of library), insert size, data format (does the customer require kinetics data) and whether it is a pooled library. When submitting the inquiry, please forward this information to APM team for evaluation. Please note that, we do not have the pooling and de-multiplex services, the
customer needs to pool their libraries in advance, and we will only release the data of the whole Cell. When generating the quotation, we need to include the library QC, sequencing, data QC and data release.
If a client sends us PCR products, can we accept this kind of samples?
- A: Yes, we can offer this service. For PacBio PCR product sequencing, the recommended sample input is >2 μg with a length of 15Kb~18Kb. Please note that we only accept linear PCR products and whole Cell orders. PCR products shorter than 1Kb cannot be acceptable. We don’t promise any data output per Cell or per sample to this service. Clients can pool their samples together by adding barcodes, and the use of PacBio's official barcode is highly recommended. The maximum number of PCR products that can be pooled in one Cell is based on the barcode number. However, considering the data output, it is highly recommended to have fewer PCR products, ideally <100 PCR products, and the size of each PCR product should be very similar within each Cell. In addition, we do not have the de-multiplex service, instead we provide whole Cell data to customers.
PacBio DNA Sequencing (Bacteria/Fungi)
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity
PacBio DNA HiFi library
HMW* Genomic DNA (Fungi/ Bacteria)
≥ 2 μg**
≥ 40 μL
≥ 50 ng/μL
OD260/280=1.75~2.0 OD260/230=1.3~2.6
NC/QC***=1.0~2.2 Fragments should be ≥ 20K
- Note:
*HMW: High Molecular Weight.
**≥2 μg: For full-cell orders with fewer than 3 samples, a minimum of 3 μg per sample is required.
***NC/QC: NanoDrop concentration/Qubit concentration.
Sequencing Strategy and Turnaround Time
Application (WOBI)
Library Type
Recommended Sequencing Depth
Turnaround Time (WOBI ≤ 10 samples)
Bacteria Genome HiFi Sequencing
HiFi library
1Gb HiFi data
20 working days
Fungi HiFi Genome Sequencing
HiFi library*
50X HiFi data
20 working days
Application (WBI)
Survey Illumina/T7
Assembly PacBio HiFi
Expected Results
Turnaround Time (WBI ≤ 10 samples)
Bacteria Complete Map
-
50X
-
40 working days
100X (1Gb)
50X
1 contig, 0 gap, BUSCO≥90%
50 working days
(including genome survey)
Fungi Fine Map
50X
<30M: Heterozygous rate＜0.5%, N50 ≥ 2 Mb (except yeast)
30-50M: Heterozygous rate＜0.5%, N50 ≥
3 Mb (≤ 10 chromosomes)
60 working days (including genome survey)
Guide to Making a Quotation
Bacteria Complete Map: Please continue to fill in 1Gb in SFDC. While we process 1Gb to ensure adequate data volume, only 50X will be delivered to customers as this fulfills all analysis requirements. To avoid confusion regarding data quantity, the Sales/TS team should modify the quotation PDF to clarify "50X sequencing depth per sample".
Analysis Contents
Standard Analysis - Bacterial Complete Map (HiFi)
Software
Data QC
Data quality control
/
Assembly
Genome assembly
HiFiasm
Plasmid sequence alignment
/
Assembly evaluation
BUSCO
Genomic composition analysis
Coding gene annotation Repeat sequence annotation Non-coding RNA
Genomics islands (GIs) Prophage
CRISPR
ISfinder Integron
GeneMarkS
RepeatMasker/ Tandem Repeats Finder tRNAscan-SE/ Rfam/ rRNAmmer IslandPath-DIOMB
PhiSpy CRISPRdigger ISfinder
INTEGRALL
Functional gene analysis
Effector: Secreted protein prediction, Secretion Systems and T3SS Effector Prediction, Secondary Metabolite Gene Cluster Analysis
SignalP/ TMHMM/ EffectiveT3/ SecReT6 v3.0
Gene function annotation: NR, GO, KEGG, COG, TCDB, CAZy, Pfam and Swiss-Prot annotation
Diamond
Virulence and pathogenicity analysis: Pathogen Host Interactions (PHI) Annotation, Virulence Factors of Pathogenic Bacteria (VFDB) Annotation, Antibiotic Resistance Genes (ARDB, CARD) Annotation
Diamond/ RGI
Genome visualization
Whole genome circle map Plasmid circle map
Circos
Methylation analysis
Detection of base modifications
Distribution of methylation motifs in GRs/IGRs Motif gene annotation
COG annotation
SMRT Link/ Circos
Methylation circle plot
Standard Analysis - Fungal Fine Map (HiFi)
Software
Data QC
Sequencing data quantity control
/
Assembly
Genome advanced assembly Assembly evaluation
HiFiasm
Genomic composition analysis
Coding genes
Repeat sequence annotation Non-coding RNA
Transdecoder/ Glimmer/ Snap RepeatMasker/TandemRepeats Finder
tRNAscan-SE/ cmsearch/ rRNAmmer/ Rfam
Functional gene analysis
Effector: Secreted protein prediction, Secondary Metabolite Gene Cluster Analysis, P450 Annotation, Transcription Factor Analysis
SignalP/ TMHMM/ antiSMASH
Gene function annotation: NR, GO, KEGG, KOG, TCDB, CAZy, Pfam and Swiss-Prot annotation
Diamond
Virulence and pathogenicity analysis: Pathogen Host Interactions (PHI) Annotation, Fungal Virulence Factors (DFVF) Annotation
Diamond
Genome visualization
Whole genome circle map
Circos
Data Delivery
WOBI projects: HiFi data with kinetics information.
WBI projects: HiFi data with kinetics information, analysis results.
- Note: Kinetics information can increase the amount of storage used by the output BAM files by up to 5 times. The final data release size should be 5X original sequencing data.
## FAQ
- Can we perform HMW DNA extraction for bacteria or fungi samples?
- A: Sorry, currently we can’t provide HMW DNA extraction. Here are some recommended kits for help: Circulomics / Qiagen Gentra Puregene / Qiagen MagAttract HMW DNA extraction kits. PacBio also provides official recommendations. Here is the link: https://extractdnaforpacbio.com
If a client is interested in bacterial methylation information, which sequencing method should we recommend: PacBio long-read sequencing or short-read WGBS?
- A: Whole Genome Bisulfite Sequencing (WGBS) is widely used for detecting 5mC in eukaryotic species, while in bacteria, the primary types of methylation are 4mC and 6mA. Based on our previous experience, WGBS is not the ideal method for analyzing bacterial methylation, and as such, we do not currently offer WGBS services for bacteria. For customers primarily interested in 4mC and 6mA, we recommend using PacBio DNA sequencing, which includes the modification analysis as part of our Bacteria Complete Map service. For more details, please check the analysis content and demo report.
If a client sends us PCR products, can we accept this kind of samples?
- A: Yes, we can offer this service. For PacBio PCR product sequencing, the recommended sample input is >2 μg with a length of 15Kb~18Kb. Please note that we only accept linear PCR products and whole Cell orders. PCR products shorter than 1Kb cannot be acceptable. We don’t promise any data output per Cell or per sample to this service. Clients can pool their samples together by adding barcodes, and the use of PacBio's official
barcode is highly recommended. The maximum number of PCR products that can be pooled in one Cell is based on the barcode number. However, considering the data output, it is highly recommended to have fewer PCR products, ideally <100 PCR products, and the size of each PCR product should be very similar within each Cell. In addition, we do not have the de-multiplex service, instead we provide whole Cell data to customers.
PacBio Full-Length RNA Sequencing
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
RIN (Agilent 2100)
Purity (NanodropTM / Agarose Gel)
A260/280=1.8-2.2
Kinnex full-length
RNA library
Total RNA
> 1.2ug
≥ 30 μL
≥ 40 ng/μL
≥ 6.5 with flat
baseline
A260/230=1.3-2.5
NC/QC* ≤ 2.0
- Note:
*NC/QC: NanoDrop concentration/Qubit concentration Recommended suspension buffer: RNase-free ddH2O
Sequencing Strategy and Turnaround Time
Application
Library Type
Recommended Sequencing Depth
Turnaround Time (< 10 samples)
WOBI
WBI
Comprehensive transcript annotation in a species
Kinnex full-length RNA library
5M HiFi reads
30 working days
45 working days
Isoform discovery of high expressed transcripts
5M HiFi reads
30 working days
45 working days
Isoform discovery and quantification of moderate-to rare transcripts
10M HiFi reads
30 working days
45 working days
Guide to Making a Quotation
The new Kinnex full-length RNA kit concatenates cDNA from different samples. Therefore, during library construction, each sample is assigned a unique barcode, and they are pooled into a single library. In this case, if the customer requires Cell sequencing, we cannot provide a standard quotation based on per-sample library preparation costs. For Cell sequencing, the total cost includes: cDNA generation cost per sample, Library preparation cost per library, and Sequencing cost per cell.
- Note: For each library, we recommend pooling 3–6 samples to ensure sufficient data per sample. The barcode system allows a maximum of 12 samples per library.
Analysis Contents
Standard Analysis- Iso-Seq
(Full-length transcriptome with reference genome)
Note
Software
1. Raw data processing and analysis
SMRT-Link
2. Alignment with reference genome
pbmm2
3. Functional annotation of transcripts
NR, KOG/COG, Swiss-prot, KEGG, NT, Pfam
Diamond blastx ncbi-blast+ blastn Hmmscan
4. Gene structure analysis
Transcriptome classification and feature analysis
Pigeon
Alternative splicing
SUPPA
Alternative polyadenylation (APA)
Tapis
Novel genes and novel transcripts prediction
NR, KOG/COG, Swiss-prot, KEGG,NT,Pfam
Tapis
Novel gene functional annotation
Diamond blastx ncbi-blast+ blastn Hmmscan
Transcription factor identification
Plants: iTAK
Animal: AnimalTFDB
LncRNA analysis
CPC2, CNCI, PLEK, PfamScan
Fusion transcript analysis
5. Gene/Transcript expression level analysis
Steps of 5-8:
10M HiFi reads is highly recommended if quantification analysis is required.
Iso-Seq data will be used for quantification analysis by default. If the customer prefers to use short-read RNA seq data for quantification, please indicate in the quotation.
HTSeq (short-read RNA-seq) IsoQuant V3.3 (Iso-Seq)
6. Differential gene/ transcript expression analysis
Biological replicates: DESeq2 No biological replicates:DEGseq Cuffdiff
7. GO enrichment analysis of differentially expressed genes (for two or more groups)
GOSeq
8. KEGG pathway enrichment analysis of differentially expressed genes (two or more groups)
KOBAS
Standard Analysis – Iso-Seq
(Full-length transcriptome without reference genome)
Note
Software
1. Raw data processing and analysis
SMRT-Link
2. Functional annotation of transcripts
NR, KOG/COG, Swiss-prot, KEGG, NT, Pfam, GO
CD-HIT
Diamond
Hmmscan HMMER
3. Structure analysis
Prediction of coding sequences (CDS)
ANGEL
Transcription factor identification
Plants: Itak
Animal: AnimalTFDB
SSR analysis
MISA
LncRNA analysis
/
4. Gene expression level analysis
Steps of 4-7:
10M HiFi reads is highly recommended if quantification analysis is required.
Iso-Seq data will be used for quantification analysis by default. If the customer prefers to use short-read RNA seq data for quantification, please indicate in the quotation.
IsoQuant
5. Differential gene expression analysis
Biological replicates: DESeq2 No biological replicates: DEGseq
6. GO enrichment analysis of differentially expressed genes (for two or more groups)
GOSeq
7. KEGG pathway enrichment analysis of differentially expressed (for two or more groups)
KOBAS
Data Delivery
Iso-Seq (Kinnex full-length RNA kit, Revio platform) WOBI project delivery: HiFi reads as default.
WBI project delivery: hifi_reads.bam, analysis results
## FAQ
For Iso-Seq, how should we deal with Fail samples?
Top up data size≤ 2M reads3M reads4M reads5M readsTop up data size≤ 2M reads3M reads4M reads5M readsA: For fail samples, we do not recommend proceeding library preparation and sequencing. Fail samples typically have low RIN value or insufficient sample amount, which can significantly impact data output and data quality. In general, customers choose Iso-Seq aim to capture the complete structure of transcripts. However, low RIN value may lead to short read length, affecting subsequent data analysis. If customers insist on going ahead, we cannot promise data output or quality. If top up is required, please refer to the pricing below.
Top up data size
≤ 2M reads
3M reads
4M reads
5M reads
Top up data size
≤ 2M reads
3M reads
4M reads
5M reads
Pricing
40% of 5M package price
60% of 5M package price
80% of 5M package price
100% of 5M package price
Top up data size
6M reads
7M reads
8M reads
9M reads
Pricing
60% of 10M package price
70% of 10M package price
80% of 10M package price
90% of 10M package price
Which service should we offer to customers when receiving an inquiry, Iso-Seq or short-read RNA sequencing? Can the previous version of Iso-Seq be analyzed together with the new Kinnex full-length RNA kit?
- A: Isoform sequencing developed by PacBio, enables the sequencing of full-length transcripts from the 5' end to the poly-A tail, providing a comprehensive view of the true transcripts expressed in cells or tissues. This is particularly beneficial for species without well-established references and genome annotations. It aid in the discovery of novel genes, isoforms, and fusion transcripts, as well as providing valuable information on homologous genes, allele expression, open reading frame prediction, alternative polyadenylation (APA), and superfamily genes. The new Kinnex full-length RNA kit is an upgraded version that concatenates different transcripts together to improve the data throughout per Cell. While maintaining the core features of the previous version, it offers comparable isoform abundance and read length distribution, as confirmed by PacBio's official data. Since PacBio has discontinued the Iso-Seq Express Oligo Kit, customers are encouraged to transition to the new Kinnex kit. The Kinnex kit is also more cost-effective, delivering a higher number of HiFi reads at a reduced price. With 10M HiFi reads, customers can access additional gene and transcript expression data without relying on short-read RNA sequencing, making it a valuable standalone option for transcriptomic studies.
Short-read RNA-seq is a more budget-friendly option that provides basic transcriptome analysis, especially for quantification analysis. However, it’s important to note that transcript quantification information will not be included in short-read RNA-seq analysis. In summary, the selection of services largely depends on the customers' research goals and budget. Before making a decision, it is essential to assess their specific needs.
- Can we find non-coding RNA information through Iso-Seq?
- A: When constructing libraries, we employ a poly-A enrichment method to specifically enrich mRNA. While a small portion of lncRNA containing a poly-A tail may also be included in the library, mRNA remains the main component of the libraries. If a customer wants to get lncRNA Information, bioinformatics approaches can be used to predict lncRNA. Our standard analysis also includes the lncRNA prediction service by using CNCI, Pfam, PLEK, and CPC. Please note that this prediction just provides complementary information alongside the mRNA data, rather than representing the
actual lncRNA in the libraries. For more accurate lncRNA information, we recommend conducting lncRNA-seq. Additionally, please be aware that we cannot obtain snRNA due to fragment size limitations. Corresponding small RNA-seq or other sequencing technique is recommended.
If the customer chooses 5M/10M HiFi reads, how much HiFi data would that correspond to, and what would be the appropriate data delivery method? Additionally, if the customer previously ordered earlier version of Iso-Seq and received subreads data, how does that compare to the equivalent amount of HiFi data?
Library TypeData format requiredDefaultSequencing data amountData release size*Data release methodKinnex full-length RNA libraryHiFi readsYes5M HiFi reads~5GbCloud/ HDDKinnex full-length RNA libraryHiFi readsYes10M HiFi reads~10GbCloud/ HDDLibrary TypeData format requiredDefaultSequencing data amountData release size*Data release methodKinnex full-length RNA libraryHiFi readsYes5M HiFi reads~5GbCloud/ HDDKinnex full-length RNA libraryHiFi readsYes10M HiFi reads~10GbCloud/ HDDA: The HiFi data size=reads number*read length. For Iso-Seq, 1.5Kb can be used for calculation. There are 2 packages available now, 5M HiFi reads≈7.5Gb HiFi data, 10M HiFi reads≈ 15Gb HiFi data. Regarding the data storage/ release size, due to the optimized file formats of Revio platform, 1Gb HiFi data can only take around 0.5Gb data storage size. Here is the detailed information.
Library Type
Data format required
Default
Sequencing data amount
Data release size*
Data release method
Kinnex full-length RNA library
HiFi reads
Yes
5M HiFi reads
~5Gb
Cloud/ HDD
Kinnex full-length RNA library
HiFi reads
Yes
10M HiFi reads
~10Gb
Cloud/ HDD
Library Type
Data format required
Default
Sequencing data amount
Data release size*
Data release method
Kinnex full-length RNA library
HiFi reads
Yes
5M HiFi reads
~5Gb
Cloud/ HDD
Kinnex full-length RNA library
HiFi reads
Yes
10M HiFi reads
~10Gb
Cloud/ HDD
- Note:
Data release size*: For the data release calculation only, does not equal to the real data output.
Subreads/GbHiFi reads/ Mb300.4600.81001.330045006Subreads/GbHiFi reads/ Mb300.4600.81001.330045006Considering that some of our customers use the previous version of Iso-Seq with subreads data, we provide the following reference. Since the conversion rate is not fixed, we cannot provide an exact value, but can only offer a rough estimate for reference.
Subreads/Gb
HiFi reads/ Mb
30
0.4
60
0.8
100
1.3
300
4
500
6
Subreads/Gb
HiFi reads/ Mb
30
0.4
60
0.8
100
1.3
300
4
500
6
- Can we provide Kinnex library preparation if the customer provides cDNA or PCR product?
- A: Kinnex library preparation requires a specific primer and amplification system to concatenate small amplicons into larger fragments. If the customer uses their own system, please take it as standard PCR products and use the SMRTbell Prep Kit 3.0 to prepare the libraries. For more details about PCR products library preparation and sequencing, please refer to page 27, FAQ 12.
General FAQ
- What is Q30?
- A: Q30 is a Q score to identify sequencing accuracy. Q30 equals 99.9% accuracy.Qphred = -10log10(e), e: error rate.
Are there any recommended kits for HMW DNA extraction?
- A: Yes, Circulomics / Qiagen Gentra Puregene / Qiagen MagAttract HMW DNA extraction kits. PacBio also provides official recommendations. Here is the link: https://extractdnaforpacbio.com.
- How to choose PacBio platform or Nanopore platform?
- A: PacBio platform carries distinct advantages of high accuracy over Nanopore platform, particularly with HiFi reads that offers average 99.9% (Q30) read accuracy. The average Q-score of Nanopore Q20+ kit, with high accuracy basecalling mode, is 14, which is lower than that of PacBio platform. Thus, in most cases, PacBio can meet customers’ requirements for variant calling or de novo assembly.
Nanopore platform also has many advantages. It provides longer reads at a lower cost, with an average N50 greater than 20K (PASS samples). Additionally, the Nanopore platform can provide more methylation information, such as 6mA, compared to the PacBio platform. Therefore, the choice between platforms should depend on the specific requirements of the projects.
PlatformSoftwareRevioSMRT® Link V13.0PlatformSoftwareRevioSMRT® Link V13.0What software and library preparation kit do we use? A: Software:
Platform
Software
Revio
SMRT® Link V13.0
Platform
Software
Revio
SMRT® Link V13.0
Library preparation kits:
Library Type
Library Prep kit
HiFi library
SMRTbell prep kit 3.0
Kinnex full-length RNA library
Iso-Seq express 2.0 (reverse transcription) Kinnex full-length RNA Kit
Sequencing related kits:
Revio polymerase kit
SPRQ polymerase kit
Sequencing plate
SPRQ sequencing plate
If a client wants to send us premade library for PacBio sequencing, what question should you ask before quotation?
- A: We need to check the species, library prep kit, library type (Kinnex Iso-Seq/bulk RNA library, standard DNA HiFi library, Kinnex scRNA library or other types of library), insert size, data format (does the customer require kinetics data) and whether it is a pooled library. When submitting the inquiry, please forward this information to APM team for evaluation. Please note that, we do not have the pooling and de-multiplex services, the
customer needs to pool their libraries in advance, and we will only release the data of the whole Cell. When generating the quotation, we need to include the library QC, sequencing, data QC and data release.
When generating a quotation, how can I select the correct data delivery type?
- A: SFDC allows you to choose data delivery type, and ‘Data requirement’ will be spliced directly. Since we no longer offer CLR library preparation and sequencing, please select HiFi reads for all projects.
Novogene Product Manual
Nanopore Sequencing
AMEA 2025.09
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclosed to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
12 Nanopore Sequencing AMEA Product Manual-2025 V1.0
Revision Number
V1.3
Issue Date
September 29, 2025
Prepared by
Liu Rui
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2024 V1.1
Page 14-FAQ 11: Update on data output and data guarantee information
Liang Yan
Liu Rui
November 21, 2024
2024 V1.2
Page 17-Analysis Content-Metagenomics English report update Page 12-FAQ 7, Page 15-FAQ 4: De novo assembly update
Page 16-Bacteria sample requirement update
Liang Yan Liu Rui
December 13, 2024
2025 V1.0
Overall update of raw data format
Page 13: Update the ultra-long sample requirement. Move metagenomics to Metagenomic Product Manual.
Liang Yan Liu Rui
June 19, 2025
2025 V1.2
Page 21-Update direct RNA Sample Requirements
Liang Yan Liu Rui
July 30, 2025
2025 V1.3
Page 21-Update direct RNA Sample Requirements
Liang Yan Liu Rui
September 29,
2025
Content
Principle of Nanopore Sequencing5
Nanopore DNA Sequencing (Human/ Plant/ Animal)9
## Sample Requirements9
Sequencing Strategy and Turnaround Time9
Analysis Contents10
## FAQ10
Nanopore Ultra-Long DNA Sequencing (Human/ Plant/ Animal)13
## Sample Requirements13
Sequencing Strategy and Turnaround Time14
Analysis contents14
## FAQ15
Nanopore DNA sequencing (Bacteria/ Metagenomics)17
## Sample Requirements17
Sequencing Strategy and Turnaround Time17
Analysis Contents17
## FAQ18
Nanopore Direct RNA Sequencing21
## Sample Requirements21
Sequencing Strategy and Turnaround Time21
Analysis Contents (Chinese report only)22
## FAQ23
General FAQ26
Principle of Nanopore Sequencing
PromethION is a series of Nanopore sequencing platforms with the highest throughput among all other Nanopore sequencing platforms. Within this series, PromethION 24 and PromethION 48 have the capability to operate up to 24 and 48 flow cells respectively. At Novogene, we use PromethION 48 platform. For PASS samples and DNA sequencing, the average read length N50>20Kb.
Nanopore is the core technology of the Nanopore sequencer and also gives its name to the company. A nanopore refers to a protein-based pore that spans an electrically resistant polymer membrane. During sequencing, when nucleic acids pass through the membrane, they cause changes in the membrane's current. These changes are detected by the Nanopore reader, allowing for the detection of base information.
Nanopore library structure:
Like short-read sequencing libraries, Nanopore sequencing libraries have a linear structure with the library DNA in the middle and sequencing adapters attached to both ends. However, Nanopore adapters are uniquely designed, incorporating a motor protein and a tether molecule. These specialized components facilitate the movement of the DNA through the Nanopore, allowing the machine to accurately sequence the base information.
Motor protein (purple) carries the DNA template and binds to the Nanopore during the sequencing. It unwinds the double-stranded DNA and guide DNA template to pass through Nanopore.
Tether molecule (orange) is used to facilitate the passage of the DNA template through the nanopore and signals capture.
Nanopore 1D library: 1D library is a type of Nanopore sequencing library. In a 1D library, only one strand of the DNA/ RNA (either the forward or reverse strand) is sequenced as it passes through the Nanopore. All the kits we use now, belong to 1D library. Other library types, such as 2D libraries, have gradually been phased out by Nanopore and are no longer used.
Basecalling: The process of basecalling involves reading the signal data and converting this into fastq files containing the nucleotide sequences and associated quality scores from the sequenced molecule. The basecallers offer three different basecalling models: a Fast model, a High accuracy (HAC) model, and Super accurate (SUP) model. The Fast model is designed to keep up with data generation on Oxford Nanopore devices (MinION Mk1C,
GridION, PromethION). The HAC model provides a higher raw read accuracy than the Fast model and is more computationally intensive. The Super accurate model has an even higher raw read accuracy and is even more intensive than the HAC model. Novogene routinely uses the HAC model to balance data accuracy with sequencing cost considerations.
Adaptive sampling: Adaptive sampling is a specialized sequencing mode that enriches regions of interest (ROIs) by depleting off-target regions. In Nanopore sequencing, the real-time nature enables us to identify whether the strand being sequenced is within the ROIs or not. If it does not belong to the ROIs, this strand will be ejected from the Nanopore, and another strand can be sequenced instead. Adaptive sampling can run in two different modes: “enrichment” and “depletion”. In “enrichment”, ROIs (typically a .bed file) are uploaded and strands that fall outside of this are rejected. In “depletion” mode, targets that are not of interest (e.g. host DNA in a host: microbiome metagenomic analysis) are uploaded and strands that fall within these regions are rejected.
File formats:
FASTQ output: Novogene delivers FASTQ files to customers by default.
POD5 output: POD5 is an Oxford Nanopore-developed file format which stores the raw sequencing data for each read, encompassing all the information necessary for in-depth analysis of nanopore sequencing data. If customers have specific analysis needs, such as methylation analysis, please indicate the release POD5 files in quotation.
FAST5 output: FAST5 files contain the raw sequencing data for each read. However, the latest version of ONT's instrument software no longer support demultiplexing of FAST5 data. While POD5 and FAST5 contain the same information (only in different formats), customers can convert POD5 to FAST5 afterward if needed. If FAST5 files are explicitly requested, additional conversion fees may apply. For further details, please consult the APM team.
BAM output: BAM files are generated when using modified base models in MinKNOW and Dorado. If customers request BAM files with modification information, please confirm the modification type with the customer and consult with the APM team for evaluation.
Nanopore DNA Sequencing (Human/ Plant/ Animal)
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity
Nanopore PromethION DNA library
HMW* Genomic DNA
≥ 8.5 μg***
≥ 50 μL
≥ 100 ng/μL
OD260/280=1.75~2.0; OD260/230=1.4~2.6; NC/QC**=0.95~3.00
Fragments should be ≥ 30K
*HMW: High Molecular Weight.
**NC/QC: NanoDrop concentration/Qubit concentration
***≥ 8.5 μg: 8.5μg is only enough for one time sequencing in one flow cell. If customers want to order 2 or more flow cells, extra 8.5μg is required for each flow cell.
-For Fail samples, resending samples is recommended. If customers choose to proceed despite the risks, flow cell sequencing will be required, as Fail samples may impact the data output of other samples within the same flow cell. While customers have the option to pool their own samples together within one flow cell.
Sequencing Strategy and Turnaround Time
Application
Recommended Sequencing Depth
Turnaround Time (≤ 5 sample)
WOBI
WBI
Human/ Plant/ Animal Whole Genome Sequencing
30X
25 working days
35 working days
Analysis Contents
Standard Analysis
Human/ Plant/ Animal Whole Genome Resequencing
Software
Data quality control: raw data processing and data statistics
Dorado & NanoPlot
Alignment with reference and statistics
Minimap2
SV calling, annotation and statistics
Sniffles, ANNOVAR
Circos plot
Circos
Customized Analysis
Human/ Plant/ Animal Whole Genome Resequencing
Software
CNV calling and statistics
CNVkit
## FAQ
- Can we offer HMW DNA extraction services for human, plant or animal samples?
- A: We don’t have HMW DNA extraction services currently. However, we can recommend some kits that may be helpful: Circulomics/ Qiagen Gentra Puregene/ Qiagen MagAttract HMW DNA extraction kits. Additionally, Oxford Nanopore provides an official community offering extensive support, including extraction protocols for various species and sample types. When receiving inquiries, please first confirm the species and sample type with the customer, then visit the community to find the appropriate protocols. The community is open for registration to those interested in Nanopore sequencing. You can access it here: https://community.nanoporetech.com/docs/prepare/extraction_protocols?from=support.
- Can we provide methylation analysis to the customer?
- A: Currently, we do not offer methylation-related analysis services. Nanopore sequencing enables the detection of methylation types such as 5mC, 5hmC,
and 6mA at single-nucleotide resolution. To meet customer needs, we can provide the original POD5 files containing raw signal data for methylation analysis. To ensure accurate data delivery, please specify the required data format in the quotation, such as “POD5+FASTQ required for this project.” If not specified in advance, POD5 files will be deleted 7 days after sequencing is completed. Note that POD5 files are approximately 20 times larger than FASTQ files, so please choose an appropriate data release method and account for additional data release costs. Additionally, the instrument can be configured to generate BAM files containing 5mC and 5hmC information. We can offer this service upon request; please confirm with the APM team and specify in the quotation that “5mC and 5hmC BAM file is required.” BAM files are approximately 3 times larger than the original data.
- What is the minimum order of Nanopore sequencing? Can we offer per Gb sequencing to customers?
- A: Please refer to the price list for detailed information on our price packages, which vary by service type. For example, for human whole genome sequencing, we recommend a minimum coverage of 10-15X for analysis, with a minimum order of 45 Gb per sample. Customers can add additional Gb based on their specific needs. For plant and animal sequencing, a minimum of 5 Gb per sample is available. For PASS samples, we guarantee data output based on the customer’s requested Gb; however, data output is not guaranteed when customers order a single flow cell. For FAIL samples, resending samples is recommended. If customers decide to proceed despite the risks, they may need to order a whole flow cell.
- What is the expected data output per flow cell, read length, and Q score of the Nanopore PromethION platform?
- A: Based on our current experience, the data output per flow cell varies depending on species type and sample quality. For human PASS samples, a single flow cell typically produces around 100 Gb, while for plant or animal PASS samples, the output is around 70-80 Gb per flow cell. The average N50 read length of PASS samples is >20Kb. In terms of data accuracy, with the new Q20+ chemistry, the average Q score can reach 14 or higher.
- Can we provide PCR product sequencing?
- A: The Nanopore platform is not recommended for sequencing PCR products. For long-read sequencing of PCR products, the PacBio platform is more suitable due to its higher accuracy. PCR amplification often introduces bias and artifacts, which can affect data accuracy; therefore, using a platform with higher precision is advisable to minimize errors. If customers still wish to use the Nanopore platform, flow cell sequencing will be required. Customers may add barcodes and pool different PCR products themselves.
Do we have premade library sequencing service?
- A: We do not offer Nanopore premade library sequencing service due to the unstable nature of Nanopore libraries. During shipment, adapters may detach from the libraries, and this problem cannot be detected through standard library QC. This often results in limited data output for customers. Therefore, we do not offer Nanopore premade library service.
- Can the Nanopore platform be used for de novo sequencing? What is the recommended sequencing depth?
- A: First, confirm the project details with the customers, such as the desired level of assembly. If customers aim to achieve contig-level or chromosome-level assembly using a single long-read sequencing platform, the Nanopore platform is not recommended. PacBio HiFi DNA sequencing provides similar read length but with much higher data accuracy, leading to more precise assembly results. If customers still prefer to use the Nanopore platform, we recommend 100X Nanopore data. For higher assembly levels, such as T2T (Telomere-to-Telomere) assembly, longer reads are needed to span large repetitive regions and fill gaps that HiFi data cannot cover. In this scenario, combining PacBio HiFi DNA sequencing with Nanopore ultra-long DNA sequencing is recommended. For diploid species, a suggested combination is 60X PacBio HiFi DNA data, 50X Nanopore ultra-long DNA data, and 100X Hi-C data. The N50 read length achieved by ultra-long service also significantly influences the assembly level, particularly for large and complex genomes. In some cases, N50>50K can’t meet customers’ requirements. Please provide details and evaluate with APM team.
Nanopore Ultra-Long DNA Sequencing (Human/ Plant/ Animal)
Ultra-long DNA sequencing utilizes ultra-high molecular weight (uHMW) DNA to prepare libraries for Nanopore sequencing. It has demonstrated the ability to produce reads with an N50 >50 kb.
## Sample Requirements
For uHMW DNA submission, please indicate the species and original sample type (tissue, cell or blood) in SIF. The PC/PM team also need to indicate this information when submitting order information since we will employ different methods to construct the library. The SQK-ULK114 targets cell and blood samples, while for other sample types, we will use the SQK-LSK114 kit. Please note that the ULK114 involves transposome-mediated cleavage of the DNA fragments, thus it requires longer fragments as input, while the advantage is a higher data output. For cell/blood samples, if they meet the requirement of
≥30μg and ≥300kb, the lab will use SQK-ULK114 to construct the library. If these samples only meet the requirement of ≥20μg and ≥100kb, the SQK-LSK114 will be used to get qualified N50 read length.
Library Type
Sample Type
Amount***
Volume
Concentration
Purity
Nanopore Ultra-Long DNA Library (N50>50K)
uHMW* Genomic DNA (DNA extracted from Tissue)
≥ 20 μg
≥ 150 μL
≥ 135 ng/μL
OD260/280=1.7-2.0 OD260/230=1.3-2.6 NC/QC**=0.95-3.00
Fragments should be ≥ 100k, no fragments below 30k
Nanopore Ultra-Long DNA Library (N50>50K)
uHMW* Genomic DNA (DNA extracted from Cell/Blood)
≥ 30 μg
≥ 300 μL
≥ 100 ng/μL
OD260/280=1.7-2.0 OD260/230=1.3-2.6 NC/QC**=0.95-3.00
Fragments should be ≥ 300k, no fragments below 30k
uHMW*: Ultra-High Molecular Weight.
NC/QC**: NanoDrop concentration/Qubit concentration
Amount***: The required amount is only enough for a single library preparation and sequencing in one flow cell. If customers require two or more flow cells, please provide an additional 20μg or 30μg DNA per library and per flow cell. The library preparation cost will be charged normally for each library.
Sequencing Strategy and Turnaround Time
ApplicationRecommended Sequencing DepthTurnaround Time (≤ 5 sample)WOBIWBIHuman/Plant/Animal Re-Seq (Structural Variants)≥ 15X40 working days50 working daysHuman/Plant/Animal De Novo Seq*60X HiFi+ 50X ONT ultra-long+ 100X Hi-CCase by CaseCase by caseApplicationRecommended Sequencing DepthTurnaround Time (≤ 5 sample)WOBIWBIHuman/Plant/Animal Re-Seq (Structural Variants)≥ 15X40 working days50 working daysHuman/Plant/Animal De Novo Seq*60X HiFi+ 50X ONT ultra-long+ 100X Hi-CCase by CaseCase by caseNote: For Nanopore ultra-long DNA sequencing service, each sample must be sequenced in a separate flow cell, and pooling multiple samples in a single flow cell is not allowed. The recommended sequencing depth provided below is for estimating the number of flow cells required per sample. Orders cannot be placed based on Gb.
Application
Recommended Sequencing Depth
Turnaround Time (≤ 5 sample)
WOBI
WBI
Human/Plant/Animal Re-Seq (Structural Variants)
≥ 15X
40 working days
50 working days
Human/Plant/Animal De Novo Seq*
60X HiFi+ 50X ONT ultra-long+ 100X Hi-C
Case by Case
Case by case
Application
Recommended Sequencing Depth
Turnaround Time (≤ 5 sample)
WOBI
WBI
Human/Plant/Animal Re-Seq (Structural Variants)
≥ 15X
40 working days
50 working days
Human/Plant/Animal De Novo Seq*
60X HiFi+ 50X ONT ultra-long+ 100X Hi-C
Case by Case
Case by case
*For T2T assembly, please check with APM team.
Analysis contents
Standard Analysis
Human/ Plant/ Animal Whole Genome Resequencing
Software
Data quality control: raw data processing and data statistics
Dorado & NanoPlot
Alignment with reference and statistics
Minimap2
SV calling, annotation and statistics
Sniffles, ANNOVAR
Circos plotCircos
## FAQ
- What is our experiencing data output per flow cell? Can we guarantee the data output?
- A: The data output per flow cell can vary significantly depending on species type and sample quality. According to our current experiences, the data output of a PASS sample is around 20Gb, with an N50>50K. However, as we have had limited projects so far, we still need to accumulate more experience to ensure consistent data yield, and we cannot guarantee the data output per flow cell. Please note that, for ultra-long sequencing, only flow cell sequencing is available, and samples cannot be pooled into a single flow cell.
Do we offer services for customers who request a longer N50 read length, such as N50>100K?
- A: Currently, we do not offer N50 >100K for DNA samples, even though our Tianjin lab has the capability to do so. The primary challenge with ultra-long DNA sequencing is obtaining high-quality DNA that is long enough for successful library preparation and sequencing. Unfortunately, due to extended shipping times, most DNA samples degrade and do not meet the QC standard. Based on our experience, achieving an N50 >100K has been difficult. However, if customers can send tissue samples to our Tianjin lab, we may be able to extract qualified uHMW DNA. Once the samples PASS QC, we can offer data with an N50 >100K. In such cases, please confirm the species, sample type, and consult the logistics team to ensure these samples can be transported to China, along with the associated shipping costs. For further details and project evaluation, please check with the APM team case by case.
- Can we offer the uHMW DNA extraction service?
- A: Our SG lab does not offer uHMW DNA extraction services. For standard ultra-long DNA sequencing service (N50>50K), we recommend using the NEB Monarch® HMW DNA Extraction Kit. For other special services, such as N50> 100K sequencing that requires DNA extraction in TJ lab, please refer to
FAQ 3 and evaluate with APM team case by case.
When should I recommend ultra-long DNA sequencing to customers instead of standard Nanopore DNA sequencing?
- A: Due to its ultra-long read length, this service is ideal for detecting large structural variants (SV) and performing de novo sequencing. For SV detection, it can identify complex variants ranging from tens to even hundreds of kilobases. If customers specifically request such results, we can recommend Nanopore ultra-long DNA sequencing. In de novo sequencing, the ultra-long reads enable coverage of large repetitive regions and fill gaps that PacBio HiFi data may not cover. For customers aiming for T2T-level assemblies, ultra-long DNA sequencing is crucial in complementing the primary assembly generated with PacBio HiFi data or other sequencing techniques. The N50 read length achieved by ultra-long service also significantly influences the assembly level, particularly for large and complex genomes. In some cases, N50>50K can’t meet customers’ requirements. Please provide details and evaluate with APM team.
Nanopore DNA sequencing (Bacteria)
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
Purity
Nanopore PromethION DNA library
HMW* Genomic DNA (Bacteria)
≥ 3.5 μg
≥ 50 μL
≥ 60 ng/μL
OD260/280=1.7~2.2; OD260/230=1.3~2.6; NC/QC**=0.95~3.00
Fragments should be ≥ 15K
HMW*: High Molecular Weight.
NC/QC**: NanoDrop concentration/Qubit concentration
Sequencing Strategy and Turnaround Time
Application
Recommended Sequencing Depth
Turnaround Time (≤ 5 sample)
WOBI
WBI
Bacteria Re-Seq
100X
25 working days
Case by case
Bacteria Complete Map
100X Nanopore data+100X illumina data
Analysis Contents
The following analysis is only available in Chinese. If customers request, please consult with the APM team.
Standard AnalysisSoftware
Bacteria Complete Map
Data quality control
NanoPlot
Genome assembly
Unicycler
Genome structure analysis
GeneMarkS RepeatMasker
Tandem Repeats Finder IslandPath-DIOMB phiSpy
-Coding gene annotation
-Repeat region annotation
-Non-coding RNA annotation
-Genomics Islands
-Prophage
Gene function annotation
SignalP
- Effector analysis
TMHMM
-Gene function annotation (NR, GO, KEGG, CAZy, TCDB, COG)
antiSMASH
- Virulence and pathogenicity analysis (PHI, VFDB, ARDB, CARD)
DIAMOND
Genome visualization
Circos
## FAQ
- Can we offer HMW DNA extraction services for bacteria samples?
- A: We don’t have HMW DNA extraction services currently. However, we can recommend some kits that may be helpful: Circulomics/ Qiagen Gentra Puregene/ Qiagen MagAttract HMW DNA extraction kits. Additionally, Oxford Nanopore provides an official community offering extensive support, including extraction protocols for various species and sample types. When receiving inquiries, please first confirm the species and sample type with the customer, then visit the community to find the appropriate protocols. The community is open for registration to those interested in Nanopore sequencing. You can access it here: https://community.nanoporetech.com/docs/prepare/extraction_protocols?from=support.
If customers want to get methylation information, what can I do?
- A: We currently do not offer methylation analysis. However, if customers are interested in methylation information, we can provide the original POD5 data for their own analysis. Depending on the algorithm used, customers can detect 6mA or 4mC methylation accordingly. To ensure accurate data delivery, please specify the required data format in the quotation, such as "POD5+fastq are required for this project." Without prior notice, POD5 files will be deleted 7 days after sequencing is completed. Please note that POD5 files are approximately 20 times larger than fastq files, so it's important to select an appropriate data release method and account for any additional data release costs.
Do we have adaptive sequencing or adaptive sampling?
- A: Adaptive sequencing is a specialized instrument configuration that enriches regions of interest by depleting off-target regions, commonly used in metagenomics to remove host data from samples. However, we do not currently offer adaptive sampling services. Adaptive sequencing requires significantly more computational resources than standard sequencing modes, leading to higher costs. We recommend using standard sequencing modes with increased data output as a more cost-effective approach to obtain effective results. For important or large projects where customers are interested in adaptive sampling, please contact the APM team for further evaluation.
Do we have any analysis services for bacteria samples?
- A: Currently, we only offer the Chinese version for bacterial complete map. The English version is under development. For customers who can accept the Chinese report, these services are available. For other important or large projects that require the English version, please consult with the APM team.
- Can we provide Nanopore sequencing services for fungal samples?
- A: Fungal Nanopore sequencing is not our standard service. We recommend PacBio HiFi DNA sequencing due to its higher accuracy, which is crucial given
the complexity of fungal genomes. If customers still prefer to use the Nanopore platform, please refer to the bacterial Nanopore sample requirements and pricing (library prep and sequencing pricing). For analysis and price, please consult with the APM team on a case-by-case basis.
Do we have premade library sequencing service?
- A: We do not offer Nanopore premade library sequencing service due to the unstable nature of Nanopore libraries. During shipment, adapters may detach from the libraries, and this problem cannot be detected through standard library QC. This often results in limited data output for customers. Therefore, we do not offer Nanopore premade library sequencing service.
Do we offer PCR product sequencing, as well as the full-length 16S sequencing?
- A: The Nanopore platform is not recommended for sequencing PCR products. For long-read sequencing of PCR products, the PacBio platform is more suitable due to its higher accuracy. PCR amplification often introduces bias and artifacts, which can affect data accuracy; therefore, using a platform with higher precision is advisable to minimize errors. If customers still wish to use the Nanopore platform, flow cell sequencing will be required. Customers may add barcodes and pool different PCR products themselves. Regarding the full-length 16S sequencing, we do not provide amplification services for full-length 16S sequencing. Customers can either choose PacBio full-length 16S sequencing or perform the amplification themselves for PCR product sequencing.
Nanopore Direct RNA Sequencing
Direct RNA sequencing enables the reading of continuous, native, full-length RNA transcripts without reverse transcription or PCR amplification. Unlike traditional RNA sequencing methods, which involve converting RNA to cDNA, direct RNA sequencing provides an accurate representation of the native RNA molecules, preserving modifications like methylation that are otherwise lost.
## Sample Requirements
Library Type
Sample Type
Amount
Volume
Concentration
RIN
(Agilent 2100)
Purity
(NanoDrop™)
Nanopore direct RNA library
Total RNA (Human)
≥ 5.5 μg
≥ 20 μL
≥ 375 ng/μL
≥ 8 with flat baseline
OD260/280=1.8-2.2; OD260/230=1.6-2.5;
NC/QC* ≤ 2
Total RNA (Animal/Plant/Fungi)
≥ 5.5 μg
≥ 20 μL
≥ 375 ng/μL
≥ 7 with flat baseline
OD260/280=1.8-2.2; OD260/230=1.6-2.5;
NC/QC* ≤ 2
Sequencing Strategy and Turnaround Time
Application
Recommended Sequencing Depth
Turnaround Time (≤ 5 sample)
WOBI
WBI
Eukaryotic direct RNA-seq
10M~20M reads/sample
(1 PromethION flow cell/ sample)
40 working days
Case by case
Analysis Contents (Chinese report only)
The following analysis is only available in Chinese. If customers request, please consult with the APM team.
Standard Analysis
Software
Data quality control
NanoFilt
Alignment with reference genome
Minimap2
Gene structure analysis
-Alternative splicing
-Novel genes and novel transcripts prediction
-Novel gene functional annotation (NR, KOG/COG, Swiss-Prot, KEGG, NT,Pfam)
-Transcription factor identification
-LncRNA analysis
SUPPA PLEK CNCI
ncbi-blast+ blastn
Quantification analysis
-Gene expression level analysis
-Differential gene expression analysis
-Enrichment analysis of differentially expressed genes (GO/ KEGG)
Salmon
Biological replicates: DESeq2 No biological replicates: DEGseq Goseq
KOBAS
Poly(A) analysis
-Poly(A) length analysis
-Differential analysis
-Association analysis between poly(A) length and expression level
NanoPolish
For the following customized analysis, if customers request, please consult with the APM team.
Customized Analysis
RNA modification analysis
Software
Data quality control
NanoFilt
Methylation site detection and motif analysis
-m5C detection and analysis
-m6A detection and analysis
- KEGG/GO enrichment analysis
-Differential methylation site analysis
Tombo MEME MINES
## FAQ
Why do we require such a large amount of total RNA, which is significantly higher than the sample input on Nanopore website?
- A: There are two input requirements recommended by Nanopore officially and it corresponds to two different pipelines. We utilize the poly(A)+RNA protocol, which entails performing poly(A) enrichment and other pre-treatments prior to the standard library preparation steps. To ensure we could get enough qualified poly(A)+RNA, 5.5μg total RNA is required.
-300ng poly(A)+RNA: Poly(A)+RNA only refers to the RNA that contains a poly(A) tail. When receiving the total RNA, we will first enrich poly(A)+RNA and then perform the library preparation.
-1μg total RNA: The total RNA will be used for library preparation directly.
Why do we choose poly(A)+RNA instead of using total RNA as the input?
- A: Poly(A)+ RNA has been shown to perform better than total RNA and is officially recommended by Nanopore. Therefore, we offer the poly(A)+ RNA pipeline as the default option. However, if customers face challenges in obtaining sufficient RNA, we can also provide the total RNA pipeline by omitting the poly(A) enrichment step. Please note that choosing the total RNA pipeline may carry potential risks, such as lower data output, so it is important to inform customers in advance and manage customer’s expectations.
- Can we provide rRNA depletion instead of poly(A) enrichment?
- A: At the moment, we do not have an rRNA depletion pipeline available. However, customers have the option to perform rRNA depletion themselves. We recommend customers to provide >600ng RNA samples after rRNA depletion step. In addition, the poly(A)+RNA has better performance than other protocols. If customers finally choose rRNA depletion method, please inform the risks in advance and manage customer’s expectations.
- What is our experience data output per flow cell?
- A: For Nanopore direct RNA sequencing, it is currently only possible to accept one sample per flow cell as there is no barcode system available now. Experience data output per flow cell: 10~20Mb reads/ flow cell with poly(A)+RNA workflow.
- Note:
-Based on our current experiences, animal samples tend to yield better than plant samples. Specifically, for mouse samples, the data output per flow cell of a PASS sample can reach up to 20Mb reads. However, the output of plant samples can vary significantly. In some species, the data output may be only 3~5Mb reads.
-The data output mentioned above refers specifically to the standard library pipeline. If skipping the poly(A) enrichment step, the data output may be reduced to approximately 2~4Mb reads.
General FAQ
Library TypeLibrary Preparation KitSequencing KitNanopore PromethION DNA librarySQK-LSK114R10.4.1(Q20+)Nanopore Ultra-Long DNA Library*SQK-LSK114 or SQK-ULK 114R10.4.1(Q20+)Direct RNA librarySQK-RNA 004FLO-PRO004RALibrary TypeLibrary Preparation KitSequencing KitNanopore PromethION DNA librarySQK-LSK114R10.4.1(Q20+)Nanopore Ultra-Long DNA Library*SQK-LSK114 or SQK-ULK 114R10.4.1(Q20+)Direct RNA librarySQK-RNA 004FLO-PRO004RAWhich kit do we use for library preparation and sequencing? A:
Library Type
Library Preparation Kit
Sequencing Kit
Nanopore PromethION DNA library
SQK-LSK114
R10.4.1(Q20+)
Nanopore Ultra-Long DNA Library*
SQK-LSK114 or SQK-ULK 114
R10.4.1(Q20+)
Direct RNA library
SQK-RNA 004
FLO-PRO004RA
Library Type
Library Preparation Kit
Sequencing Kit
Nanopore PromethION DNA library
SQK-LSK114
R10.4.1(Q20+)
Nanopore Ultra-Long DNA Library*
SQK-LSK114 or SQK-ULK 114
R10.4.1(Q20+)
Direct RNA library
SQK-RNA 004
FLO-PRO004RA
*Nanopore Ultra-Long DNA Library: Different kits will be used depending on the sample type. For samples extracted from blood and cells, the SQK-ULK114 kit will be applied, while for other sample types, SQK-LSK114 will be used.
- Can we offer premade library sequencing service?
- A: We do not offer Nanopore premade library sequencing service due to the unstable nature of Nanopore libraries. During shipment, adapters may detach from the libraries, and this problem cannot be detected through standard library QC. This often results in limited data output for customers. Therefore, we do not offer Nanopore premade library sequencing service.
Do we offer PCR product sequencing service?
- A: The Nanopore platform is not recommended for sequencing PCR products. For long-read sequencing of PCR products, the PacBio platform is more suitable due to its higher accuracy. PCR amplification often introduces bias and artifacts, which can affect data accuracy; therefore, using a platform with higher precision is advisable to minimize errors. If customers still wish to use the Nanopore platform, flow cell sequencing will be required. Customers may add barcodes and pool different PCR products themselves.
- Can we offer extraction service for customers?
- A: We don’t have extraction services currently. Oxford Nanopore provides an official community offering extensive support, including extraction protocols for various species and sample types. When receiving inquiries, please first confirm the species and sample type with the customer, then visit the community to find the appropriate protocols. The community is open for registration to those interested in Nanopore sequencing. You can access it here: https://community.nanoporetech.com/docs/prepare/extraction_protocols?from=support. For the uHMW DNA extraction, we recommend using the NEB Monarch® HMW DNA Extraction Kit. The detailed protocols can also be found in Nanopore community.
Novogene Product Manual
Single Cell Sequencing
AMEA 2025.09
(This product manual is strictly confidential and intended solely for internal use within the AMEA region. The contents must not be shared with any external parties without prior written approval from the APM Director. For any product-related inquiries, please contact the APM Team.)
Product Manual Revisions
Subject
Novogene Product Manual –Single Cell Sequencing
Revision Number
2025 V1.0
Issue Date
September 2025
Prepared by
Jing Fei
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2023 V1.0
Pg 5 – Add Single Cell Service Overview Pg 6 – Revise Sample Requirement
Pg 17-20 – Add Single Cell Immune Profiling (VDJ) product Pg 21-26 – Add Single Cell Long Read Transcriptome product Pg 27-30 – Add Single Cell Spatial Transcriptome product
Tianran Shi
Sep 2023
2024 V1.0
Pg 28-31- Delete Single Cell Spatial Transcriptome product
Tianran Shi
June 2024
2025 V1.0
Pg 10 – Add Tested Sample Type
Pg 27 – Add Single nuclei concentration and cell recovery target Pg 27-29 – Add Single Cell Epi ATAC-seq
Pg 34-38 – Add Sample Preparation and Delivery Guideline
Pg 39-44 – Add Appendix (Sample Inquiry Evaluation Form, Sample
Submission Form, Service User Agreement, Selected Publications Mentioning Novogene)
Jing Fei
September 2025
Contents
Single Cell Service Overview6
Single Cell 3’/5’ Gene Expression Sequencing7
## Sample Requirements (SG/Japan lab)7
Single Cell or Nuclei Concentration and Cell Recovery Target8
GEM Generation and Library Construction Strategy8
Sequencing Strategy and Turnaround Time8
Analysis Contents9
Cell Ranger9
Standard Analysis9
Tested Sample Types10
10x Genomics User Manual11
## FAQ11
Single Cell Immune Profiling (VDJ)22
## Sample Requirements (SG lab)22
Sequencing Strategy and Turnaround Time22
Analysis Contents23
10x Genomics User Guide24
## FAQ25
Single Cell Epi ATAC-seq27
## Sample Requirements27
Single Nuclei Concentration and Cell Recovery Target27
GEM Generation and Library Construction Strategy28
Sequencing Strategy and Turnaround Time28
10x Genomics User Guide28
## FAQ28
Single Cell Long Read Transcriptome30
## Sample Requirements30
Sequencing Strategy and Turnaround Time30
Analysis Contents31
## FAQ32
Sample Preparation and Delivery Guideline34
Frozen Tissue34
Frozen Single Cell Suspension35
Fresh Tissue37
Appendix39
Sample Inquiry Evaluation Form39
Sample Submission Form (customer facing)40
Cryopreserved Single Cell Service User Agreement40
Frozen Tissue Single Nuclei Service User Agreement42
On-site Service User Agreement (For Single Cell ATAC-seq Service)43
6Selected Publications mentioning Novogene44
## Single Cell Service Overview
Single Cell Services
3’ Gene Expression
5’ Gene Expression + VDJ
(TCR and/or BCR)
Single Cell ATAC*
Single Cell Long Read Sequencing
(10x + Nanopore)
Available workflows and Lab
Fresh Single Cell suspension;
Frozen single-cell suspension (SG/Japan); Frozen Tissue (SG)
Frozen / fresh Single Cell suspension (SG)
Frozen Tissue (SG)
Frozen/ fresh Single cell suspension (SG/Japan)
ONT Library prep: Tianjin lab
Starting sample
Single cell; Single nucleus
Single cell
Single nucleus
Single cell
Species
Species with reference genome
Human and mouse
Species with reference genome
Sequencing configuration
NovaSeq PE150
NovaSeq PE50
Single cell GEX: NovaSeq PE150
Nanopore: PromethION
Data recommendation
50,000 read pairs/cell
(120-150G/sample, 8000 cells/sample)
GEX: 50,000 read pairs/cell (120-150G/sample)
VDJ: 5,000 read pairs/cell (15-20G/sample)
25,000read pairs/nucleus (200M reads/sample, 8000 cells/sample)
Single cell GEX: 100-120G/sample Nanopore:
1 flowcell/sample
Data Analysis
Cellranger report
Standard Analysis
Cellranger report
Standard Analysis
- Note:
* We can provide single cell ATAC and single cell gene expression services separately at SG lab.
Single Cell 3’/5’ Gene Expression Sequencing
Single Cell Sequencing reveals the full complexity of cellular diversity compared to bulk sequencing. It is primarily employed to solve complications related to the study of unusual cell types, cell-lineage associations, and samples of heterogeneous nature. By doing the in-depth single-cell sequencing, the cell functions of individual cells can be explored easily and efficiently.
Application: Profiling of cellular heterogeneity, novel targets, and biomarker in each cell from a heterogeneous cell population.
## Sample Requirements (SG/Japan lab)
Sample Type
Sample Amount Requirement
Other Requirements
Fresh/ Frozen single cell
Single Cells ≥ 1,000,000
Recommend two 1.5 mL cryovials
Cell viability >85% before freezing Cell viability >70% received at lab Cell diameter: 5-30 μm
Frozen tissue*
Tissue weight >= 200 mg (minimum 100mg)
Recommend at least two pieces of tissue per sample, in separate cryovials
Do NOT rinse tissues prior to freezing Freeze directly in liquid nitrogen and store it in -
80 ℃ or dry ice until use.
Fresh tissue**
Tissue weight >= 200 mg (minimum 100mg) Recommend at least two pieces of tissue per sample, in separate cryovials
Must be processed within 48hrs of harvest
Fresh single nuclei suspension***
Single Cells ≥ 1,000,000
Cell viability <10% Nuclei diameter: 5-30 μm
- Note:
* Frozen tissue – The Singapore CSA team provides nuclei isolation services.
** Fresh tissue – For Singapore samples sent to Singapore lab. Japan projects require consultation with the APM team during pre-sales.
*** Fresh Single nuclei suspension – on-site service only, as single nuclei cannot be frozen or shipped by ice. Novogene will not guarantee the results
as we don’t have proper QC metrics for nuclei quality.
Single Cell or Nuclei Concentration and Cell Recovery Target
Below are the concentration requirements to achieve target cell recovery:
For a target recovery of 10,000 cell or nuclei/sample (GEM-X chemistry), we need the cell/nuclei concentration at 700–1,200 cells/µl, with a total of ~100,000 cell/nuclei (or ~100 µl).
For a target recovery of 20,000 cell or nuclei/sample (GEM-X chemistry only), we need the cell/nuclei concentration at 1,300–1,600 cells/µl, with a total of ~150,000 cell/nuclei (~100 µl).
GEM Generation and Library Construction Strategy
The single cell 3’/5’ gene expression service is available exclusively as an in-lab service.
Kit versions
Target Recovery Cells
Service
GEM-X 3’ gene expression kit GEM-X 5’ gene expression kit
Up to 20,000 cells or nuclei/sample
In-lab service
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Data Recommendation
Turnaround Time (≤ 5 samples)
10x Single Cell 3’ /5’ Gene Expression
Illumine NovaSeq PE150/ DNBseq
50,000 read pairs/cell 120 Gb raw data/ sample
WOBI
WBI
16 working days
18 working days (Cell Ranger) 22 working days (Standard
Analysis)
Analysis Contents Cell Ranger
Standard Analysis (Cell Ranger)
Software
Demultiplex BCL files from a sequencer into FASTQs
Cell Ranger
Alignment of reads to the genome
Gene expression quantification
Summary metrics (sequencing quality, number of cells detected, the mean reads per cell, and the median genes detected per cell et al.)
Clustering analysis which groups together cells that have similar expression profiles
Differentially expression analysis between clusters
Visualization
Standard Analysis
Software
Demultiplex BCL files from a sequencer into FASTQs
Sequencing data processing and quality control:
Data pre-procession Alignment to the genome Calling cells and UMI counting Quality control
Summary metrics (Sequencing, Alignment, Calling cells and UMI counting and Quality control summary)
Cell Ranger STAR
Identification of highly variable genes (HVGs)
Seurat
Cell Subpopulation Identification Principal component analysis (PCA) Identify clusters of cells
Dimensionality reduction and Visualization
Seurat
Marker gene detection (Differentially expression analysis between clusters)
Seurat
Enrichment Analysis GO Enrichment
KEGG Pathway Enrichment Reactome Enrichment
Functional Annotation of Transcription Factor Protein-Protein Interaction Network Analysis
clusterProfiler TFCat
STRING, BLAST
Tested Sample Types
ServiceSpeciesSample Sources3’ Gene ExpressionMouseLung, Colon, Liver, Brain (go through nuclei isolation)HumanPBMC5’ Gene ExpressionHumanNasopharyngeal carcinoma.Nuclei isolation (frozen tissue)MouseLiver, Brain, Kidney, LungServiceSpeciesSample Sources3’ Gene ExpressionMouseLung, Colon, Liver, Brain (go through nuclei isolation)HumanPBMC5’ Gene ExpressionHumanNasopharyngeal carcinoma.Nuclei isolation (frozen tissue)MouseLiver, Brain, Kidney, LungWe have extensive experience (100+ sample types) with various tested sample types at our Tianjin lab. Below is a list of sample origins that were tested at the Singapore CSA lab:
Service
Species
Sample Sources
3’ Gene Expression
Mouse
Lung, Colon, Liver, Brain (go through nuclei isolation)
Human
PBMC
5’ Gene Expression
Human
Nasopharyngeal carcinoma.
Nuclei isolation (frozen tissue)
Mouse
Liver, Brain, Kidney, Lung
Service
Species
Sample Sources
3’ Gene Expression
Mouse
Lung, Colon, Liver, Brain (go through nuclei isolation)
Human
PBMC
5’ Gene Expression
Human
Nasopharyngeal carcinoma.
Nuclei isolation (frozen tissue)
Mouse
Liver, Brain, Kidney, Lung
Tissue dissociation (fresh tissue)
Mouse
NPC, Lung, Colon, Liver
10x Genomics User Manual
Service
10x Genomics User Guide
GEM-X 3’ gene expression
Chromium GEM-X Single Cell 3' Reagent Kits v4
GEM-X 5’ gene expression
Chromium GEM-X Single Cell 5' Reagent Kits v3
## FAQ
What are the sample requirements for 10x Single Cell 3’/5’ Gene Expression experiment?
- A: For single cell experiment, cell viability is most important. Therefore, we typically advise the following sample requirements:
Cell viability to be >70%
Clear from debris, clean background
Cell size to be <30um
Cell suspension buffer – PBS (Mg & Ca free) + 0.04% BSA (400 µg/ml) or media that’s free from surfactant (i.e Tween 20), EDTA (> 0.1mM), or
magnesium (> 3mM)
To target 10,000 cells/sample, ideally 700 -1,200 cells/ul, around 100ul (sufficient for cell counter and another run)
To target 20,000 cells/sample, ideally 1,300–1,600 cells/µl, around 100ul (sufficient for cell counter and another run)
Will the nuclei isolated using the Chromium Nuclei Isolation Kit be compatible with Feature Barcoding, CellPlex, CRISPR screening, or VDJ profiling?
- A: The process of nuclei isolation removes outer cell membranes and cytoplasmic compartments, therefore:
Feature barcoding for cell surface protein or antigen specificity is not compatible with nuclei.
VDJ capture from nucleic transcripts is challenging and not currently supported.
The use of nuclei from frozen tissue with CellPlex is not currently supported. Nuclei isolated from fresh tissue with the Chromium Nuclei Isolation Kit are untested and unsupported with CellPlex.
What type of samples do we recommend for isolating nuclei?
Sample TypeReason not recommended send frozen cellsHeart, Muscle, Adipose, MacrophagesCell diameter is larger than chip pipeline diameterLiverLiver parenchymal cells are too fragile, and most will rupture during processingBrain/NeuronNerve cells are relatively sensitive, and the expression of stress genes changes greatly during digestion. Neuron has finger-like projections may pose an issue for captureKidneys, Thyroid, PancreasCell suspension preparation is not ideal due to the abundance of endogenous enzymes, etc.Sample TypeReason not recommended send frozen cellsHeart, Muscle, Adipose, MacrophagesCell diameter is larger than chip pipeline diameterLiverLiver parenchymal cells are too fragile, and most will rupture during processingBrain/NeuronNerve cells are relatively sensitive, and the expression of stress genes changes greatly during digestion. Neuron has finger-like projections may pose an issue for captureKidneys, Thyroid, PancreasCell suspension preparation is not ideal due to the abundance of endogenous enzymes, etc.A: Those sample types are recommended to isolate nucleus for single cell gene expression library prep. Due to nucleus is very tricky, it cannot be frozen. And if the customer's tissue sample has been cryopreserved, only cell nuclei can be extracted and cannot be prepared into a frozen cell suspension anymore.
Sample Type
Reason not recommended send frozen cells
Heart, Muscle, Adipose, Macrophages
Cell diameter is larger than chip pipeline diameter
Liver
Liver parenchymal cells are too fragile, and most will rupture during processing
Brain/Neuron
Nerve cells are relatively sensitive, and the expression of stress genes changes greatly during digestion. Neuron has finger-like projections may pose an issue for capture
Kidneys, Thyroid, Pancreas
Cell suspension preparation is not ideal due to the abundance of endogenous enzymes, etc.
Sample Type
Reason not recommended send frozen cells
Heart, Muscle, Adipose, Macrophages
Cell diameter is larger than chip pipeline diameter
Liver
Liver parenchymal cells are too fragile, and most will rupture during processing
Brain/Neuron
Nerve cells are relatively sensitive, and the expression of stress genes changes greatly during digestion. Neuron has finger-like projections may pose an issue for capture
Kidneys, Thyroid, Pancreas
Cell suspension preparation is not ideal due to the abundance of endogenous enzymes, etc.
Chromium Nuclei Isolation Kit Sample Prep User Guide
- What is the 10x Single Cell 3’ Gene Expression project workflow?
- A: Project Design —Frozen cells/Frozen tissue/On-site service*— Sample Quality Control — cDNA amplification and QC — Library Construction —
Library Quality Control — Sequencing — Data Quality Control — Bioinformatics Analysis
*We provide on-site service to process your single cell samples in your lab to ensure high cell viability for single cell experiment. On-site service applicable for Singapore & Japan customers only.
What RNA types can be profiled with the 10x Single Cell 3’ Gene Expression solutions?
- A: Any cell type that expresses polyadenylated mRNA molecules is compatible with this single cell RNA-seq workflow.
Is it possible to capture microRNAs in the Gene Expression assays?
- A: Mature microRNA (miRNA) transcripts lack a polyA tail and will therefore not be captured by either the Single Cell 3' or 5' Gene Expression assays or the Visium Spatial assay.
Are 10x Single Cell 3’/5’ Gene Expression libraries strand-specific?
- A: Yes, 10x single cell solutions are strand-specific libraries. Cell Ranger 'Count' counts sense-strand reads only.
- What is the difference between Single Cell 3' and 5’ Gene Expression libraries?
- A: The two assays are similar but capture different ends of the polyadenylated transcript in the final library. Both solutions use polydT primer for reverse transcription, although in the 3' assay the polydT sequence is located on the gel bead oligo, while in the 5' assay the polydT is supplied as an RT primer. A template switching oligo (TSO) is used in both workflows to reverse transcribe the full-length transcript.
After amplifying the cDNA, molecules are randomly fragmented under conditions that favor 300-400 bp length fragments. Downstream of fragmentation, only transcripts containing both (1) a 10x Barcode AND (2) an Illumina Read 2 adaptor, which is ligated on to the cDNA after fragmentation, will be amplified during the Sample Index PCR. This results in final 10x libraries that either represent the 3' end of the transcript (as the 10x Barcode is adjacent to the polyA tail on the 3' end of the transcript) or the 5' end of the transcript (as the 10x Barcode is adjacent to the TSO and the 5' end of the transcript).
A schematic diagram comparing the final library construct for the two assay schemes is illustrated below.
GEM-X Single Cell 3’ v4 (Dual index) Gene Expression Library:
GEM-X Single Cell 5’ v3 Gene Expression Library:
- What is the recommended sequencing depth for Single Cell 3' and 5' Gene Expression libraries?
- A: For new sample types, we recommend sequencing a minimum of 50,000 read pairs/cell for Single Cell gene expression libraries. The sequencing depth required for a particular experiment, however, will depend on:
Sample type (different samples will have more or less RNA per cell) The experimental question being addressed.
- What is the sequencing configuration for 10x single cell 3’ gene expression libraries?
- A: The Chromium™ Single Cell 3’ Gene Expression Solution with Feature Barcode technology produces Illumina® sequencer-ready libraries. Supported Sequencers: Illumina® NovaSeq
Recommended Sequencing: Minimum 50,000 read pairs/cell*
**Shorter transcript reads may lead to reduced transcriptome alignment rates. Cell barcode, UMI and Sample index reads must not be shorter than indicated. Any read can be longer than recommended. Customer can sequence on Novoaseq6000 PE150 using default configuration, then trim to the read length indicated in form.
More details please refer to the 10x Genomics User Guide: Chromium GEM-X Single Cell 3' Reagent Kits v4
Where can I find 10x index oligos?
- A: Dual index sample index plates: Each well is a mix of 2 oligonucleotides, one of which contains a unique i7 sample index and one of which contains a unique i5 sample index.
Single index sample index plates: Each well is a mix of 4 oligonucleotides, each of which contains a unique i7 sample index. Using 4 oligos per sample index ensures that the i7 index read is balanced across all 4 bases during sequencing.
The sample index sequences can be found here.
- Can we guarantee the Q30 of the Single Cell 3’ Gene Expression raw data?
- A: Due the read1 and read2 are shorter than PE150, the Q30 might slightly lower than 75%, we are unable to guarantee the Q30 of raw data. We can only guarantee the Q30 after data trimming under the PE150 sequencing strategy.
- How to raise quotation in SFDC system?
- A: Please refer to WeDrive for the details process in SFDC system.
https://doc.weixin.qq.com/sheet/e3_ANEAKQYTAN0SvYalwhARriAu61bzx?scode=AJgAAQcaAAw0hH8pcR Please choose the correct process with different labs. We provide both WOBI and WBI product.
If customer requires WBI product, TS/Sales can choose Cell Ranger or standard analysis. Please note standard analysis includes Cell Ranger analysis contents, so no need to include 2 processes in the quotation.
Where can I find the html of cell ranger report? Does standard analysis include cell ranger report as well?
- A: You can find the html of cell ranger report in ‘2.4 Pre-procession HTML Summary’ in the standard analysis report. Standard analysis result includes cell ranger report. If client ordered standard analysis, they don’t need to order cell ranger analysis anymore.
Are we able to compare the differences among samples and groups?
- A: The marker gene results in our standard analysis is based on differentially expression analysis between clusters within sample/group.
If a customer wants to compare between samples/groups (control vs treatment) or compare between clusters (sample1 cluster1 vs sample2 cluster1) please ask APM for evaluation.
What species can we analyze?
- A: The species with reference genome with well annotation can do single cell Cell Ranger analysis and standard analysis.
- What is the analyzing software: Cell Ranger and Loupe Browser?
- A: Cell Ranger is a set of analysis pipelines that will automatically generate expression profiles for each cell and identify clusters of cells with similar expression profiles.
https://support.10xgenomics.com/single-cell-gene-expression/software/pipelines/latest/what-is-cell-ranger Loupe Browser, a visualization software, can be used to interactively explore the results.
https://support.10xgenomics.com/single-cell-gene-expression/software/visualization/latest/what-is-loupe-cell-browser
What does the “Barcode Rank Plot” mean in Cell Ranger report?
- A: Barcode Rank Plot: All 10x Barcodes detected during sequencing (~100k) are plotted in decreasing order of the number of UMIs associated with that barcode. The number of UMIs detected in each GEM is used by Cell Ranger to determine which GEMs likely contain a cell. GEMs containing cells are expected to have a greater number of transcripts (and thus UMIs) associated with them than non-cell containing GEMs.
Typical Sample (left figure): A steep drop-off is indicative of good separation between the cell-associated barcodes and the barcodes associated with empty GEMs. An ideal Barcode Rank plot has a distinctive shape, which is referred to as a “cliff and knee”. The blue-to-gray transition (green arrow) is referred to as the cliff; the solid gray is referred to as the knee (blue arrow).
Compromised Sample (Right figure): Round curve and lack of steep cliff may indicate low sample quality or loss of single-cell behavior. This can
be due to a wetting failure, premature cell lysis, or low cell viability.
What customized analysis can we offer?
- A: (1) Cell type annotation: customer needs to provide a list of cell types and corresponding marker genes in order to perform cell annotation analysis. For example:
Pseudotime and Trajectory analysis.
Differential gene analysis across different clusters or groups.
Cell-Cell Communication analysis.
- How is Chromium iX different from the Chromium Controller?
- A: Chromium iX is our most flexible instrument, with the most advanced hardware and wireless connectivity. It runs all single cell assays, including new high-throughput assays for Single Cell Immune Profiling and Single Cell Gene Expression. Chromium Controller runs our low- and standard-throughput assays. It does not run high-throughput assays.
- Can we process neutrophils (or other granulocytes) using 10x Single Cell applications?
- A: Single-cell analysis of neutrophils and granulocytes generally remains a significant challenge. This is because neutrophils (and other granulocytes) have relatively low RNA content and relatively high levels of RNases and other inhibitory compounds, resulting in fewer transcripts detected in GEMs, and less usable sequencing reads. Furthermore, neutrophils are particularly sensitive to degradation after collection.
Immediate processing is critical. Ideally, neutrophils should be processed immediately after collection, and any delay longer than two hours is likely to result in a failed run. Isolation of neutrophils from frozen samples may also present significant challenges, and fresh samples are always preferred.
More details in the 10x Genomics note:
https://kb.10xgenomics.com/hc/en-us/articles/360004024032-Can-I-process-neutrophils-or-other-granulocytes-using-10x-Single-Cell-applications
- Can we process organoid tissues for 10x single cell assays?
- A: Organoids are 3-dimensional (3D) cell cultures that represent fundamental characteristics and cellular organization of an organ. These 3D cultures provide useful information regarding the biology of healthy or diseased organ models. Organoids are generated using relevant cell culture strategies
based on the cells of origin. For example, organoid cultures could be generated using iPSCs, hESCs, or adult stem cells. Note that we have not specific protocol for organoids, customers can refer to the following guide from 10x Genomics:
Technote: Are there any recommendations for working with organoid tissue for 10x single cell assays
Single Cell Immune Profiling (VDJ)
Single Cell Sequencing reveals the full complexity of cellular diversity compared to bulk sequencing. It is primarily employed to solve complications related to the study of unusual cell types, cell-lineage associations, and samples of heterogeneous nature. By doing the in-depth single-cell sequencing, the cell functions of individual cells can be explored easily and efficiently.
Application: Analyze full-length, paired B-cell or T-cell receptors, antigen specificity, and gene expression, all from a single cell
## Sample Requirements (SG lab)
Sample Type
Sample Amount Requirement
Other Requirements
Fresh single cell suspension*
Single Cells ≥ 1,000,000
Cell viability >80% Nuclei diameter: 5-30 μm
Frozen single cell
Single Cells ≥ 1,000,000
Recommend two 1.5 mL cryovials
Cell viability >85% before freezing Cell viability >70% received at lab Cell diameter: 5-30 μm
- Note:
* Fresh single cell suspension – For Singapore samples sent to Singapore lab
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Data Recommendation
Turnaround Time (≤ 5 samples)
10x Single Cell 5’ Gene Expression Library
NovaSeq PE150
50,000 read pairs/cell Recommend 120 Gb raw data/ sample
WOBI
WBI
10x Single Cell TCR/BCR library
NovaSeq PE150
5,000 read pairs/cell (15-20G/sample)
16 working days
25 working days (Standard Analysis)
Analysis Contents
Standard Analysis
Standard Analysis BCR/TCR
Software
Demultiplex BCL files from a sequencer into FASTQs
Cell Ranger
Assemble and annotate contigs
Call cells and generate clone type
Summary metrics (sequencing quality, number of cells detected, the mean reads per cell, and the number of V-J spanning productive paired cells et al.)
Distribution of clonotypes (summary of the top 10 clonotypes, cell counts, proportions, and CDR3 amino acid sequences)
Unique clonetype Summary
scRepertoire/immunarch
Clonotypes Statistics
CDR3 Length Statistics
Clonotypes for displaying VJ Gene Combinations
Display of VJ gene abundance for each sample
Analysis of highly expressed clonotypes by multi-sample comparison
10x Genomics User Guide
Chromium Single Cell V(D)J Reagent Kits
Service
10x Genomics User Guide
GEM-X 5’ gene expression
Chromium GEM-X Single Cell 5' Reagent Kits v3
## FAQ
Is Single Cell Immune Profiling compatible with nuclei?
- A: We are unable to run single cell immune profiling with nuclei.
We have found that obtaining VDJ data from nuclei is challenging, and we cannot guarantee VDJ assay performance when using nuclei instead of cells. The primary reason for this is the transcript loss that occurs from nuclei isolation. VDJ transcripts tend to be more lowly expressed, even in cells. Isolating only nuclei means that RNA contained in the cytoplasm is lost, which results in reduced transcripts available for capture and analysis. Additionally, increased ambient RNA in the cell suspension resulting from a typical nuclei isolation can make it more challenging for the Cell Ranger VDJ algorithm to accurately assemble contigs and determine which GEMs contain T/B cells which do not.
https://kb.10xgenomics.com/hc/en-us/articles/360019890751-Is-Single-Cell-Immune-Profiling-compatible-with-nuclei-
- Can I study T and/or B cell immune repertoires, gene expression from the same cells?
- A: Yes. The Single Cell Immune Profiling Solution offers the option to generate: an enriched T cell library and/or an enriched B cell library, and/or a 5’
gene expression library, as well as a Cell Surface Protein library from the same cells.
To determine what kits are needed to complete your desired experiment, please visit 10x genomics 'Product List' page for our Single Cell Immune Profiling. This will allow you to select the kits needed for your specific project needs.
Please refer to the price list if additional T-cell or B-cell library is required.
If both BCR and TCR are selected, please clarify with the customer which should be prioritised in case of limited cDNA quantity.
- Can I sequence V(D)J-enriched and 5' Gene Expression libraries on the same lane?
- A: Yes. V(D)J-enriched libraries and 5’ Gene Expression libraries can be pooled for sequencing, but note the depth requirements and sequencing configurations are different. We recommend 5,000 reads pairs/targeted cell for V(D)J-enriched libraries and a minimum of 20,000 read pairs/cell for 5’ Gene Expression libraries, and therefore recommend adjusting the pooling ratio accordingly. (For example, if the two library types have the same number of cells targeted and the same library concentration, 4-fold more 5' Gene Expression Library should be mixed with the V(D)J-enriched Library to obtain 4x more reads per cell.)
Our recommended parameters for sequencing V(D)J and 5' Gene Expression libraries together is as follows:
v3 (dual index): Read 1: 28 cycles, i7 Index: 10 cycles, i5 Index: 10 cycles, Read 2: 90 cycles
What are the recommended T and B cell enrichment protocols?
- A: https://kb.10xgenomics.com/hc/en-us/articles/115002488623-Recommended-T-and-B-cell-enrichment-protocols
What report does Novogene provide for Immune Profiling (VDJ) product?
- A: 5’ gene expression: cell ranger report for gene expression only
5’ gene expression + TCR or BCR: Standard analysis report for gene expression and TCR/BCR
- How to raise quotation in SFDC system?
- A: Please refer to WeDrive for the details process in SFDC system. https://doc.weixin.qq.com/sheet/e3_ANEAKQYTAN0SvYalwhARriAu61bzx?scode=AJgAAQcaAAw2nV4ilL
Please choose the correct process with different labs. TS/Sales can choose the process based on client’s requirement.
Single Cell Epi ATAC-seq
Chromatin organization compacts meters of DNA into the nucleus, making just a small fraction of DNA accessible for transcription within each cell. The Next GEM Epi ATAC (Assay for Transposase Accessible Chromatin) solution provides a robust and scalable approach to map the epigenetic landscape at single cell resolution. Using a transposase enzyme to preferentially tag accessible DNA regions with sequencing adaptors, researchers can now generate sequencing-ready libraries and identify open chromatin regions.
Application: Analyze chromatin accessibility and cellular epigenetic heterogeneity. Perform epigenetic profiling for hundreds to tens of thousands of nuclei, enabling detection of rare cells. Examine non-coding sequences to discover cis-regulatory elements and drivers of gene expression differences between cell types and states.
## Sample Requirements
Sample Type
Sample Amount Requirement
Other Requirements
Frozen tissue
Tissue weight >= 200 mg (minimum 100mg) Recommend at least two pieces of tissue per sample, in separate cryovials
Do NOT rinse tissues prior to freezing. Freeze directly in liquid nitrogen and store it in -80 ℃ or dry ice until use.
Single Nuclei Concentration and Cell Recovery Target
Below are the concentration requirements to achieve target cell recovery:
For a target recovery of 10,000 nuclei per sample, we need the nuclei concentration at 3,080–7,700 nuclei/µl, with a total of ~350,000 cell/nuclei (or ~100 µl).
GEM Generation and Library Construction Strategy
Kit versions
Target Recovery Cells
Service
Next GEM Single Cell ATAC kit
500 to 10,000 nuclei per sample
In-lab service
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Data Recommendation
Turnaround Time (≤ 5 samples)
10x Single Cell ATAC
Illumina PE50
25,000 read pairs/nucleus (200M reads/sample)
WOBI
WBI
35 working days
Cellranger report Standard Analysis
10x Genomics User Guide
Chromium Single Cell ATAC Reagent Kits
Service
10x Genomics User Guide
Next GEM Single Cell ATAC-seq
Chromium Next GEM Single Cell ATAC Reagent Kits v2
## FAQ
- How does scATAC-Seq differ from bulk ATAC-Seq?
ATAC-Seq is a bulk sequencing technology used to assess genome-wide chromatin accessibility. One caveat with bulk ATAC-Seq is that the chromatin signal is averaged for all cells in a sample, limiting insights into low-abundance phenotypes or rare populations of cells. scATAC-Seq enables researchers to interrogate the chromatin landscape of hundreds to thousands of individual cells at the single-cell level.
Is scATAC-seq right for the customer?
Please refer to the 10x Genomics blog
https://www.10xgenomics.com/blog/is-single-cell-epigenomics-right-for-me-atac-ing-your-research-questions-for-deeper-insights
Single Cell Long Read Transcriptome
Combining long-read sequencing with single cell assays enables the unambiguous identification of alternative splicing at single cell resolution. Traditional single cell assays have relied on short-read sequencing, which loses information about transcript isoforms relevant to health, development, and disease. Application: Analysis of gene expression and genomic variation at the single-cell level
Characterization of transcript isoforms relevant to health, development, and disease in single cell level.
## Sample Requirements
Sample Type
Sample Amount
Cell Viability/Concentration
Remark
Single cell suspension
Single Cells ≥ 100,000
Viability ≥ 80%,
Diameter: 5-40 μm
—
cDNA
≥ 50 ng
Peak Size: 1-1.8 kb Concentration > 2 ng/ul
No more than 2 months storage under
-20℃/-80℃
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Data Recommendation
Turnaround Time (≤ 5 samples)
10x Single Cell 3’ Gene Expression Library
NovaSeq PE150
100Gb or 120Gb/sample
WOBI
WBI
30 working days
40 working days (Cell Ranger) 45 working days (Illumina Standard Analysis)
Nanopore cDNA Library
PromethION
1 ONT flowcell/sample
20 working days
25 working days (wf-single-cell) 35 working days (Nanopore
Standard Analysis)
Analysis Contents
Standard Analysis (wf-single-cell)
Software
Data QC
wf-single-cell
Identify the cell barcode and UMI sequences present in nanopore sequencing reads
Summary metrics: read quality, number of cells, genes and transcripts identified within each sample, median genes per cell, and sequence saturation
UMAP projections
Standard Analysis (Nanopore data only)
Software
Data QC
NanoPlot
Mapping and Quantification
wf-single-cell
Dimensionality reduction, clustering, and differential analysis Base on gene
Base on transcripts
Seurat
Enrichment analysis： GO Enrichment
KEGG Pathway Enrichment Reactome Enrichment
clusterProfiler
Alternative Splicing
isoswitch
Fusion gene analysis (advance analysis, please evaluate with APM)
Fusion gene analysis
## FAQ
- What is the Nanopore cDNA library prep kit and sequencing kit?
- A: Nanopore cDNA libraries were prepared with full-length cDNA generated from Chromium Single Cell 3' Reagent Kits (v3.1) using the Nanopore Ligation Sequencing Kit V14 SQK-LSK114 according to the manufacturer’s protocol. And was sequenced on an Oxford Nanopore Technologies’ PromethION sequencer with R10 kit.
- What is the workflow of single cell long read transcriptome sequencing?
- A:
Does single cell long read transcriptome seq applies to other 10x single cell libraries?
- A: It applies to 10x single cell 3’ gene expression only.
Where can I find the html of wf-single-cell report? Does standard analysis include wf-single-cell report as well?
- A: You can find the html of wf-single-cell report in 4. Mapping and Quantification in standard analysis report. Standard analysis result includes wf-single-cell report. If client ordered standard analysis, they don’t need to order wf-single-cell analysis anymore.
- What is our species experience?
- A: We have experience on human and mouse.
Sample Preparation and Delivery Guideline
Frozen Tissue
Whole frozen tissues are accepted for 10x single-nuclei 3' gene expression and single cell ATAC.
Frozen tissues are processed for nuclei isolation, as cell integrity is not well-maintained during thawing of whole tissues. For tissues that contain large cells >30um or cells that are sensitive to dissociation, single-nuclei sequencing may be preferable.
Freezing Method
The recommended tissue weight for nuclei isolation is >200mg. Do NOT rinse tissues prior to freezing. Immediately freeze the tissues as quickly as possible after harvesting/dissection. Place the tissue in a cryotube and seal tightly (with parafilm wrapped around the cap). Either submerge in liquid nitrogen (preferred) or a liquid nitrogen cooled bath, or place deep in a bucket of dry ice. Wait at least 2 to 3 minutes for the tissue to completely freeze and transfer the tube containing the tissue to vapor-phase liquid nitrogen for long term storage. For shorter-term storage, the tissue may be stored at - 80°C.
Storage
For long-term storage (>2 days), it is strongly recommended to store tissue samples in liquid nitrogen to avoid degradation. If liquid nitrogen storage is not available, store the sample at -80°C or colder.
Please note that tissues frozen and stored for less than one month generally yield better sample quality after processing.
Shipping Conditions
Place tubes into a 50 ml conical tube. Ship the materials with sufficient dry ice (5 LB per day) in a polystyrene box.
Resources
10x Genomics Q&A: How can I ship tissue for 3’ Gene Expression profiling?
Frozen Single Cell Suspension
Frozen single-cell suspensions are accepted for 10x 3' and 5' single-cell gene expression (including TCR/BCR), and Nanopore long reads sequencing. Single-cell suspension may be obtained from cell culture, or isolated from whole, fresh tissues via tissue dissociation methods.
Tissue dissociation to single-cell suspension (for fresh tissue)
We can provide tissue dissociation service for fresh tissue from Singapore customers. Different tissue of sample type may require different dissociation protocol or handling. Please consult the 10x Genomics sample prep recommendations (https://support.10xgenomics.com/single-cell-gene-expression/sample-prep) to ensure that the protocol/ cell types are compatible with single cell sequencing.
Process fresh tissues for dissociation to single cells as soon as possible after harvesting/dissection. Harvest and dissect tissues under RNase-free and sterile conditions.
Count Cells and perform viability assessment (e.g., using cell stains such as Acridine Orange/Propidium Iodide, or Trypan blue).
Inspect cell suspension under microscope for debris, cell morphology, clumping cells.
Harvesting cultured cells to single-cell suspension (for cultured cells)
Harvest cells according to cell-specific procedures [see also 10x Demonstrated Protocols for cultured cell lines].
Centrifuge and remove culture medium & resuspend in fresh culture medium (if required).
Count cells and perform viability assessment (e.g., using cell stains such as Acridine Orange/Propidium Iodide, or Trypan blue).
Cell enrichment (if applicable)
We don’t provide cell enrichment service (e.g., cell sorting FACS).
Cryopreservation Method
Cryopreservation methods should be adapted for the specific cell types of interest. The following are general steps to observe:
Centrifuge cells gently and remove existing media/PBS.
Resuspend cells in culture medium with cryoprotectant: e.g., 10% DMSO or cell-specific freezing medium. Please refer to 10x Genomics article and protocol file from https://kb.10xgenomics.com/hc/en-us/articles/360029138592-How-should-I-store-my-single-cell-suspension-for-scRNA-seq
Use a freezing container to hold the cells in cryovials at -80 °C overnight. This ensures rate-controlled freezing to maximize viability after thawing.
Storage
After freezing, store 1.5mL cryovials in liquid nitrogen for at least one (1) week before shipping to Novogene Singapore Lab.
Shipping Conditions
Please arrange shipment for samples on dry ice, sufficient for shipment to Novogene lab. Make sure samples are securely tightened, and make sure to place the samples in a sealed bag.
Thaw, Wash and Resuspension at CSA lab
All cells will be washed with and resuspended in PBS + 0.04% BSA at CSA lab. If the customer intends to wash and resuspend cells in a different buffer, please contact our technical specialist.
Resources
10x Genomics Protocol: Cell Preparation for Single Cell Protocols
10x Genomics Protocol: Fresh Frozen Human-Mouse Cell Line Mixtures for Single Cell RNA Sequencing (CG00014) 10x Genomics Q&A: Can I store samples in a tissue storage solution
Fresh Tissue
Fresh tissues must be processed within 48 hours of harvest and storage in the preservation solution. We only accept fresh tissues from Singapore and Japan customers, which will be processed at the SG/Japan Novogene lab.
Storage
Tissue preservation solution will be provided to customers for the storage of samples prior to sample collection. Store the tissue preservation solution at -20°C, away from light, when not in use. Thaw completely on ice before use:
Ensure tissue is free of microbial contamination, necrotic tissue, or residual blood. Wash with pre-chilled PBS if necessary.
Be quick when transferring samples to the preservation solution. Avoid having samples exposed for long periods of time.
Cut tissue into pieces approximately 0.5 cm in diameter or smaller and immerse one piece in the preservation solution inside the tube. Storage of larger pieces may lead to lower cell viability.
(c) Label the tube with sample name, date and time of harvest and keep it on ice or at 4°C prior to transportation and processing - Do not freeze the tissue.
Shipping Condition
As tissues must be processed within 48 hours of harvest and storage in the preservation solution, Technical Specialist please arrange for the courier to collect the samples immediately after harvest to ensure tissue viability.
Samples should be shipped on wet ice to maintain viability. DO NOT use dry ice.
Resources
10x Genomics Q&A: Can I store samples in a tissue storage solution
## Appendix
Sample Inquiry Evaluation Form
General questionsSpecies*Tissue typee.g., brain, liver.Sample submission typee.g., Cryopreserved single cell samples? Fresh Tissue? Frozen Tissue?Number of samplesService required3’ gene expression (GEM-X),5’ gene expression +TCR/BCR (GEM-X), scATAC,NGS + Nanopore or Nanopore only, others need to indicateEstimated sample delivery time***Will the samples be sent all at once or in multiple batches?Questions for 3’/5’gene expressionTarget cell numbersWill samples go through cell sorting by the customer or notQuestions for Nanopore long read service**Which 10x Genomics product is the cDNA derived frome.g., 3’ gene expression, 3’ gene expression + cell surfaceproteincDNA storage time and temperaturee.g., 2 months under -80°CData analysisCell Ranger report or not, need Nanopore analysis or notGeneral questionsSpecies*Tissue typee.g., brain, liver.Sample submission typee.g., Cryopreserved single cell samples? Fresh Tissue? Frozen Tissue?Number of samplesService required3’ gene expression (GEM-X),5’ gene expression +TCR/BCR (GEM-X), scATAC,NGS + Nanopore or Nanopore only, others need to indicateEstimated sample delivery time***Will the samples be sent all at once or in multiple batches?Questions for 3’/5’gene expressionTarget cell numbersWill samples go through cell sorting by the customer or notQuestions for Nanopore long read service**Which 10x Genomics product is the cDNA derived frome.g., 3’ gene expression, 3’ gene expression + cell surfaceproteincDNA storage time and temperaturee.g., 2 months under -80°CData analysisCell Ranger report or not, need Nanopore analysis or notPlease collect the following information when submitting an inquiry case, so that the Product Manager can properly evaluate the feasibility and avoid repeated follow-ups with the customer, saving time and improving efficiency.
General questions
Species*
Tissue type
e.g., brain, liver.
Sample submission type
e.g., Cryopreserved single cell samples? Fresh Tissue? Frozen Tissue?
Number of samples
Service required
3’ gene expression (GEM-X),
5’ gene expression +TCR/BCR (GEM-X), scATAC,
NGS + Nanopore or Nanopore only, others need to indicate
Estimated sample delivery time***
Will the samples be sent all at once or in multiple batches?
Questions for 3’/5’
gene expression
Target cell numbers
Will samples go through cell sorting by the customer or not
Questions for Nanopore long read service**
Which 10x Genomics product is the cDNA derived from
e.g., 3’ gene expression, 3’ gene expression + cell surface
protein
cDNA storage time and temperature
e.g., 2 months under -80°C
Data analysis
Cell Ranger report or not, need Nanopore analysis or not
General questions
Species*
Tissue type
e.g., brain, liver.
Sample submission type
e.g., Cryopreserved single cell samples? Fresh Tissue? Frozen Tissue?
Number of samples
Service required
3’ gene expression (GEM-X),
5’ gene expression +TCR/BCR (GEM-X), scATAC,
NGS + Nanopore or Nanopore only, others need to indicate
Estimated sample delivery time***
Will the samples be sent all at once or in multiple batches?
Questions for 3’/5’
gene expression
Target cell numbers
Will samples go through cell sorting by the customer or not
Questions for Nanopore long read service**
Which 10x Genomics product is the cDNA derived from
e.g., 3’ gene expression, 3’ gene expression + cell surface
protein
cDNA storage time and temperature
e.g., 2 months under -80°C
Data analysis
Cell Ranger report or not, need Nanopore analysis or not
*The species must have reference genome with annotation. We only have experience on human and mouse
**Nanopore single cell long read transcriptome sequence only applies to 10x genomics 3’ gene expression. Not applies to 10x genomics 5’ gene
expression or other single cell platform (e.g., BD Rhapsody)
***We may not have 5’ gene expression and VDJ enrichment kit in stock. Please give the Product Team advance notice about sample delivery time. We need at least 1 month to purchase the kit.
Sample Submission Form (customer facing)
This form will be mandatory for every confirmed project that has been assigned a Project Number, and where sample processing will take place at the CSA lab. Please ensure that this link is shared with your customers after a project has been assigned a Project Number.
Novogene Single Cell RNA-seq Gene Expression Service 2025 V1 Novogene Single Cell ATAC-seq Service 2025 V1
Cryopreserved Single Cell Service User Agreement
If light microscope images of the single cell suspension prior to freezing do not meet the requirements (insufficient cell concentration or total cell count, low viability (<70%), clumping cells, poor cell morphology or debris), Novogene reserves the right to reject the samples. In this case, the customer will need to re-prepare the sample.
Sample viability is vital for processing. If sample viability is measured to be <70% at the initial QC step, the samples will not be processed. You will be contacted by our Technical Specialist/ Product Manager to ask if you are willing to proceed with the scRNA-seq experiment. If no samples were processed, Novogene reserves the right to stop the experiment and charges will apply (USD 80 per sample). Please note that the TAT will increase by one (1) week if the customer chooses to proceed with the second (backup) vial.
If preliminary results obtained through our services do not meet Novogene's standard requirements, final data analysis results cannot be guaranteed.
Single cell RNA-seq sample requirements:
Viability: Samples should have a viability of >70%. A lower viability may result in reduced cell recovery or difficulty in interpreting the result.
Cleanliness: Ensure that the samples are clear from debris, with a clean background.
Cell Size: The cell size should be <30 µm.
Suspension Buffer: PBS (Mg & Ca free) + 0.04% BSA (400 µg/ml), or a media free from surfactants (such as Tween 20), EDTA (> 0.1mM), or magnesium (> 3mM).
Cell Concentration:
For a target recovery of 10,000 cells:
700–1,200 cells/µl, with a total of ~100,000 cells (or ~100 µl).
For a target recovery of 20,000 cells (GEM-X only):
1,300–1,600 cells/µl, with a total of ~150,000 cells (~100 µl).
If the results obtained through our services do not meet the customer's expectations of the customer stops the experiment prior to completion, please note that there will be a charge for parts of the experiments that has been performed. The following charges will apply should the service be stopped at the following steps:
Sample Processing: USD 80 per sample for Cryopreserved Single Cell samples
GEM Generation: 70% of 10X Single Cell Gene Expression Library Service
cDNA Amplification and Library Preparation: 100% of 10X Single Cell Gene Expression Library Service.
Please note that samples will NOT be returned after the service is complete. Samples will be destroyed 60 days after the delivery of the final report. Additionally, any samples that have been in possession of Novogene for over 4 months without proceeding with library preparation/sequencing will also be subject to destruction.
All data will be deleted 30 days after data delivery. Please contact your Novogene representative if you wish to retain the data beyond 30 days. Additional cost will be incurred for the data storage.
All analytical services are used for research purposes. If the result of this service is used for purposes other than research, Novogene is not responsible for any loss or damage caused thereby.
Frozen Tissue Single Nuclei Service User Agreement
By submitting samples to Novogene for nuclei isolation, you agree to the use of our validated protocol. Post processing, we will perform quality control on the samples to determine if samples are clean, debris-free nuclei suspensions suitable for capture.
If the samples do not meet the requirements as stated, Novogene reserves the right to reject them. Customers will need to re-prepare the sample and reschedule or proceed at their own risk without guarantee of results, and charges may apply.
If preliminary results do not meet Novogene's standards, final data analysis results cannot be guaranteed. Single Nuclei RNA-seq sample requirements:
Viability: A recommended viability of single nuclei suspension is <10%.
Cleanliness: Ensure that the samples are clear from debris, with a clean background.
Nuclei Quantity and Concentration:
For a target recovery of 10,000 nuclei:
700–1,200 cells/µl, with a total of ~100,000 nuclei (or ~100 µl).
For a target recovery of 20,000 nuclei (GEM-X only):
1,300–1,600 cells/µl, with a total of ~150,000 nuclei (~100 µl).
Visualization and Quality Assessment: Light microscopy will be employed to visualize the quality of the nuclei suspension. Healthy nuclei should appear round and smooth, and the suspension should be free of clumps and debris
If services are stopped prematurely, charges will apply based on completed steps:
Sample Processing: 100% of Nuclei Isolation service
GEM Generation: 70% of 10X Single Cell Gene Expression library service
cDNA Amplification and Library Preparation: 100% of 10X Single Cell Gene Expression library service.
Please note that samples will NOT be returned after the service is complete. Samples will be destroyed 60 days after the delivery of the final report. Additionally, any samples that have been in possession of Novogene for over 4 months without proceeding with library preparation/sequencing will also be subject to destruction.
All data will be deleted 30 days after data delivery. Please contact your Novogene representative if you wish to retain the data beyond 30 days. Additional cost will be incurred for the data storage.
All analytical services are used for research purposes. If the result of this service is used for purposes other than research, Novogene is not responsible for any loss or damage caused thereby.
On-site Service User Agreement (For Single Cell ATAC-seq Service)
Before proceeding with the service, we will confirm the quality (cell count/ viability and cell size) of the samples (QC). Please note that there may be variations to the final count and viability compared to manual counting. If counting is performed by the customer due to naturally low cell counts from single cell isolation, microscope images of the single cell suspension will need to be shared with Novogene to ensure that the suspension is clean and free of debris before proceeding.
If the samples do not meet the requirements (insufficient cell concentration or total cell count, low viability (<70%), clumping cells, poor cell morphology or debris), Novogene reserves the right to reject the samples. In this case, the customer will need to re-prepare the sample and arrange
for another date of experiment. If the customer chooses to proceed with risk, the results cannot be guaranteed, and charges may apply.
If preliminary results obtained through our services do not meet Novogene's standard requirements, final data analysis results cannot be guaranteed.
If the results obtained through our services do not meet the customer's expectations or the customer stops the experiment prior to completion, please note that there will be a charge for parts of the experiment that has been performed. The following charges will apply should the service by stopped at the following steps:
GEM Generation: 70% of 10X Single Cell Gene Expression library service
cDNA Amplification and Library Preparation: 100% of 10X Single Cell 3' Gene Expression library service.
Please note that samples will NOT be returned after the service is complete. Samples will be destroyed 60 days after the delivery of the final report. Additionally, any samples that have been in possession of Novogene for over 4 months without proceeding with library preparation/sequencing will also be subject to destruction.
All data will be deleted 30 days after data delivery. Please contact your Novogene representative if you wish to retain the data beyond 30 days. Additional cost will be incurred for the data storage.
All analytical services are used for research purposes. If the result of this service is used for purposes other than research, Novogene is not responsible for any loss or damage caused thereby.
6 Selected Publications mentioning Novogene
Published Year
Application
Journal
Region of Corresponding
Author
Title
2025
Neuroscience
Nature Protocols
Singapore
Retina-specific laminin-based generation of photoreceptor progenitors from human pluripotent stem cells under xeno-free and chemically defined conditions
2025
Immunology
INTERNATIONAL IMMUNOLOGY
Japan
TLR7 responses in glomerular macrophages accelerate the progression of glomerulonephritis in NZBWF1 mice
2024
Immunology
JOURNAL OF HEPATOLOGY
Singapore
Single-cell landscape of functionally cured chronic hepatitis B patients reveals activation of innate and altered CD4-CTL-driven adaptive immunity
2024
Developmental
biology
Nature
Communications
Singapore
Lgr5 marks stem/progenitor cells contributing to epithelial and
muscle development in the mouse esophagus
2024
Neuroscience
Nature Communications
Japan
Selective vulnerability of parvocellular oxytocin neurons in social dysfunction
2024
Immunology
JOURNAL OF CLINICAL
BIOCHEMISTRY AND NUTRITION
Japan
Single-Cell Analysis Reveals Islet Autoantigen’s Immune
Activation in Type 1 Diabetes Patients
2024
Immunology
PROCEEDINGS OF THE NATIONAL ACADEMY OF SCIENCES OF THE UNITED STATES OF
AMERICA
Australia
Extra islet expression of islet antigen boosts T cell exhaustion to partially prevent autoimmune diabetes
2023
Developmental biology
GENOME BIOLOGY
Tai Wan
Single-cell transcriptomics unveils xylem cell development and evolution
2023
Stem cell biology
Science
China Mainland
A population of stem cells with strong regenerative potential discovered in deer antlers
2023
Immunology
Immunity
China Mainland
Multi-omics blood atlas reveals unique features of immune and platelet responses to SARS-CoV-2 Omicron breakthrough infection
2023
Developmental biology
Developmental Cell
Singapore
Single-nucleus sequencing deciphers developmental trajectories in rice pistils
2023
Cancer research
Science Advances
Hong Kong
Hypoxia-inducible factor orchestrates adenosine metabolism to promote liver cancer development
2023
Immunology
Frontiers in Endocrinology
Japan
Bioinformatic analysis reveals potential relationship between chondrocyte senescence and protein glycosylation in
osteoarthritis pathogenesis
2022
Neurodegenerati ve diseases
Int J Mol Sci
Singapore
Single-Cell Transcriptome of Wet AMD Patient-Derived Endothelial Cells in Angiogenic Sprouting.
2022
Immunology
EMBO reports
China Mainland
Endothelial-immune crosstalk contributes to vasculopathy in nonalcoholic fatty liver disease
2021
Cardiovascular research
Biochemical and Biophysical Research Communications
China Mainland
Single-cell analysis reveals the purification and maturation effects of glucose starvation in hiPSC-CMs
2021
Cardiovascular
research
Advanced Science
China Mainland
Characterization of cellular heterogeneity and an immune
subpopulation of human megakaryocytes
2021
Immunology
Cell death & disease
China Mainland
Single cell transcriptional zonation of human psoriasis skin identifies an alternative immunoregulatory axis conducted by
skin resident cells
2021
Immunology
Nature communications
China Mainland
Single-cell transcriptomic analysis reveals disparate effector differentiation pathways in human Treg compartment
2021
Cancer research
Journal of hepatology
China Mainland
Single-cell RNA-sequencing atlas reveals an MDK-dependent
immunosuppressive environment in ErbB pathway-mutated gallbladder cancer
2021
Immunology
Nature communications
China Mainland
Single-cell RNA-seq reveals fibroblast heterogeneity and
increased mesenchymal fibroblasts in human fibrotic skin diseases
Novogene Product Manual
Spatial Gene Expression Sequencing
AMEA 2024.08
(This manual is for AMEA use only. The information in this product manual is strictly confidential and should not be disclose to any external party without prior written consent from the APM director. If you have any questions about the products, please consult APM team.)
Product Manual Revisions
Subject
Novogene Product Manual –Single Cell Spatial Transcriptome Sequencing
Revision Number
2024 V3.0
Issue Date
Aug 2024
Prepared by
Tianran Shi
Reviewed by
Liang Yan
Revisions
Revision Number
Revised Content
Revised by
Revision Date
2024 V2.0
Pg 4-Add spatial service overview
Pg 5-Update the sample requirement for CytAssist FFPE spatial library Pg 14-17-Add Visium HD product
Tianran Shi
2024.06
2024 V3.0
Update Spatial Gene Expression Service Overview Pg 19-21 Add FFPE Stereo-seq product details
Tianran Shi
2024.08
Contents
Spatial Gene Expression Service Overview4
Spatial Gene Expression for FFPE – 10x CytAssist5
## Sample Requirements (Tianjin lab)5
Sequencing Strategy and Turnaround Time6
Analysis Contents6
## FAQ7
Spatial Gene Expression for FFPE – 10x Visium HD14
## Sample Requirements (Tianjin lab)14
Sequencing Strategy and Turnaround Time14
Analysis Contents15
## FAQ15
Spatial Gene Expression for FFPE – Stereo-seq18
## Sample Requirements (Tianjin lab)18
Sequencing Strategy and Turnaround Time19
Analysis Contents19
## FAQ19
## Spatial Gene Expression Service Overview
Service
Sample type
Species
Resolution
RNA Quality
Chip Size/Capture Size
Tissue
Permea-bilization
Target
Visium Spatial
(V1)
Fresh Frozen
No limit
55 μm
RIN≥7
6.5mm*6.5mm
Y
Whole Transcriptome
Visium CytAssist (V2)
Frersh Frozen
Human or Mouse
55 μm
RIN≥7
6.5mm*6.5mm 11mm*11mm
N
Protein coding genes in humans (18,000+)
and mice (19,000+)
FFPE
55 μm
DV200≥30%
FFPE (Visium HD)
2 μm
DV200≥30%
6.5mm*6.5mm
Stereo-seq
Fresh Frozen
No limit
220 nm
RIN≥7
1cm*1cm
Y
Whole Transcriptome
Stereo-seq
FFPE
No limit
220 nm
DV200≥30%
1cm*1cm
N
Coding and non-
coding RNAs
Xenium
Fresh Frozen FFPE
Human or Mouse
100 nm
RIN≥4 DV200≥30%
10.45mm*22.45mm
_
Human or Mouse
Nanostring DSP WTA
Fresh Frozen FFPE
_
ROI
RIN≥7 DV200≥40%
33.3mm*14.1mm
N
Protein coding genes in humans (18,000+)
and mice (20,000+)
If customer send fresh frozen tissue for spatial gene expression, please ask APM for evaluation.
Spatial Gene Expression for FFPE – 10x CytAssist
Break through the barriers that once hindered spatial analysis of gene expression in formalin-fixed paraffin-embedded (FFPE) tissue sections and unveil the hidden insights within your samples with Visium Spatial Gene Expression for FFPE. By merging the advantages of histological techniques with the vast throughput and investigative capabilities of RNA sequencing in FFPE tissue samples, Visium Spatial Gene Expression for FFPE enhances traditional pathologist-led analysis. Profile RNA expression across entire tissue sections with high resolution, encompassing more than 18,000 genes in human and mouse FFPE samples, to gain spatial insight into gene expression patterns.
## Sample Requirements (Tianjin lab)
Sample Type
Sample Amount
Preservation
Sample QC
Shipping
FFPE block (recommended)
1 block, FFPE block must be contained on plastic dehydrating box, otherwise could not be installed on
the sectioning device
After embedding store at 4°C, protected from light
DV200%≥30%
4°C or Room Temperature
FFPE slide
5-10 FFPE(10μm thickness) scrolls in tube for sample QC；
2-4 FFPE(5μm thickness) tissue sections on glass
slides, for library prep*
Dry and sealed, storage time at 4°C < 14 days
DV200%≥30%
4°C or Room Temperature
*From FFPE section to library prep, try to keep the interval within 14 days as much as possible.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data
Species
Turnaround Time (<4 samples)
10x CytAssist FFPE spatial gene expression library
NovaSeq PE150
25,000 read pairs/tissue-covered spot
~50 Gb/sample
Human or Mouse
WOBI
WBI
28 working
days
35 working
days
Analysis Contents
Standard Analysis
Software
Data QC
Mapping and Quantification
Space Ranger
Dimensionality Reduction, Clustering, and Differential analysis Graphclust clustering
K-means clustering
Space Ranger
Seurat Analysis PCA analysis
Spatial variable gene expression analysis Clustering and dimensionality reduction analysis
Seurat
Differential Expression Gene Analysis (DEG) DEGs clustering heatmap
Spatial distribution of DEGs Violin plot
t-SNE and UMAP dimensional reduction visualization
edgeR Seurat
Functional Enrichment Analysis： GO enrichment
KEGG pathway enrichment Reactome enrichment
clusterProfiler
## FAQ
- How should I fix and embed my tissue for Visium CytAssist for FFPE?
- A: https://kb.10xgenomics.com/hc/en-us/articles/9838406043149-How-should-I-fix-and-embed-my-tissue-for-Visium-CytAssist-for-FFPE-
What glass slides are compatible with Visium CytAssist Spatial Gene Expression assays?
- A:https://kb.10xgenomics.com/hc/en-us/articles/7776523750029-What-glass-slides-are-compatible-with-Visium-CytAssist-Spatial-Gene-Expression-assays-
Use this guide (CG000548) to determine if the tissue section is located in an area that results in successful analyte transfer and imaging.
- How do I transport my tissue slide to another facility when tissue has already been placed?
- A: The following steps should be taken to transport plain glass slides with tissue sections placed:
Dry the Slide at 42°C for 3 hours and store the slide in a desiccator at room temperature for at least 12 hours (and no longer than 2 weeks). After drying, slides can be shipped in a slide mailer with desiccant pouches. Ensure that the slide mailer generates a tight seal.
Include ice packs if drastic temperature changes are anticipated during transportation.
What tissue types have been validated for Visium CytAssist Spatial Gene Expression FFPE?
- A: Healthy tissues from mouse have been validated following the product documentation. A list of tissues tested that consistently generated high quality data with the Visium CytAssist Spatial Gene Expression for Fixed Frozen assay along with links to available public facing datasets for exploration can be found here: Visium CytAssist Spatial Gene Expression for Fixed Frozen Tested Tissue List.
- How is tissue preparation similar and different between Visium for FFPE (v1) and Visium CytAssist for FFPE?
- A: Both chemistry versions utilize human or mouse FFPE samples as inputs. For the CytAssist assay, FFPE blocks or archived sections on Superfrost glass slides can be used.
For the Visium for FFPE product, section placement and on-slide workflow steps occur on the Visium Spatial Gene Expression Slide. In contrast, the tissue used for the CytAssist for FFPE assay is placed on plain glass slides, and probes are transferred to the Visium CytAssist Spatial Gene Expression Slide by the Visium CytAssist instrument.
For the Visium for FFPE assay, larger tissues or blocks should be trimmed or scored to fit within the capture area. For the CytAssist for FFPE assay, if using larger tissues or blocks, they do not need to be trimmed.
The area of interest will need to be within the compatible region of the slide, centered within the gasket of the Tissue Slide Cassette, and centered within the alignment guides on the Tissue Slide stage.
Are the Visium CytAssis Slides reusable?
- A: The Visium CytAssist Spatial Gene Expression for FFPE 6.5 mm & 11 mm Slides are one-time use only regardless if probes are transferred to one or both capture areas. We recommend that customers send samples in multiples of 2, if it is not a
multiple of 2, your sample has to do library prep with other projects, we are unable to promise the turnaround time.
Comparison of Visium Spatial Gene Expression for FFPE (“Direct placement”) and Visium CytAssist Spatial Gene Expression for FFPE ("CytAssist-enabled").
- A: The Visium CytAssist Spatial Gene Expression for FFPE assay is designed to analyze mRNA in tissue sections derived from formalin fixed & paraffin embedded (FFPE) tissue samples, using probes to target the whole transcriptome. Visium CytAssist is a compact instrument designed to simplify the Visium workflow by facilitating the transfer of transcriptomic probes from tissue slides to Visium slides. This enables spatial profiling insights to be gained from an expanded range of FFPE samples, including archived tissue blocks and slides.
Workflow comparison:
Assay comparison:
Direct Placement
CytAssist-enabled
Tissue Types
Freshly placed FFPE sections
Freshly placed FFPE sections Archived hematoxylin & eosin (H&E) or
immunofluorescence (IF) + DAPI stained and imaged
sections
Slide Types
Visium Spatial Gene Expression Slides
Visium CytAssist Spatial Gene Expression Slides v2
Superfrost Plus Slides
DV200
≥ 50%
≥ 30%
Tissue Optimization
Required
Not Required
Capture region
4
2
Capture area*
6.5mm*6.5mm
11mm*11mm
Probe set
A pair of probes per gene
Three pair of probes per gene
Probe set details
Human Probe Set V1
19,144 gene_ids targeted by 19,902 probes Mouse Probe Set V1
20,551 gene_ids targeted by 20,873 probes
Human Probe Set V2
18,536 genes targeted by 54,018 probes Mouse Probe Set V1
20,551 gene_ids targeted by 20,873 probes
We have V2 Visium CytAssist Slide (6.5mm * 6.5mm) only. We don’t offer V1 and V2 11mm * 11mm slide unless an inquiry evaluation is confirmed by APM team.
Visium Gene Expression Slide:
The capture area is 6.5 x 6.5 mm. There are a total of 4992 total spots per capture area and each spot is 55 µm in diameter with a 100 µm center to center distance between spots.
Visium CytAssist Gene Expression Slide (V2):
- How does the Human Transcriptome Probe Panel v2 differ from the Human Transcriptome Probe Panel v1?
- A: Below is the high-level differences between two Human Transcriptome Probe Panels used with Visium Spatial Gene Expression for FFPE and Visium CytAssist Spatial Gene Expression assays:
There are now primarily three probe pairs designed against each gene instead of a single probe pair. A small portion of the highest expressing genes contains a single probe pair (<10% of genes).
~54,000 probe pairs are used to detect >18,000 genes. Now includes Nuclear-encoded mitochondrial genes.
- What is the recommended sequence configuration and sequence depth of 10x Spatial Transcriptome?
- A: 10x single cell spatial transcriptome requires: read1-28 cycles, i7 index-10 cycles, i5 index-10 cycles, read2-50 cycles. We suggest using NovaSeq PE150 then do data trimming.
Example of Sequence depth:
Estimate the approximate Capture Area (%) covered by the tissue section.
Calculate total sequencing depth= (Coverage Area x total spots on the Capture Area) x 25,000 read pairs/spot Example calculation for 60% coverage:
(0.60 x 5,000 total spots) x 25,000 read pairs/spot=75 million total read pairs for that sample Visium CytAssist Spatial Gene Expression Reagent Kits User Guide (CG000495)
- How many cells are captured in a single spot?
- A: The number of cells captured in a single spot is based on the tissue type, cell size, and section thickness; this is generally between 1-10 cells. With our in-house control sample mouse brain, sectioned to 10 um thickness, we typically see between 1-10 cells assayed per spot.
Where can I find the html of Space Ranger report? Does standard analysis include Space Ranger report as well?
- A: You can find the html of Space Range report in ‘4.1.1Reference genome alignment’ in the standard analysis report. Standard analysis result includes Space Ranger report. If client ordered standard analysis, they don’t need to order Space Ranger analysis anymore.
Spatial Gene Expression for FFPE – 10x Visium HD
Visium HD empowers a new era of spatial discovery, enhancing proven whole transcriptome spatial analysis with single cell–scale resolution, enabling continuous tissue coverage, and delivering best-in-class data with innovative probe-based chemistry and a Visium CytAssist-enabled workflow.
## Sample Requirements (Tianjin lab)
Sample Type
Sample Amount
Preservation
Sample QC
Shipping
FFPE block (recommended)
1 block, FFPE block must be contained on plastic dehydrating box, otherwise could not be installed on
the sectioning device
After embedding store at 4°C, protected from light
DV200%≥30%
4°C or Room Temperature
FFPE slide
5-10 FFPE(10μm thickness) scrolls in tube for sample QC；
2-4 FFPE(5μm thickness) tissue sections on glass
slides, for library prep*
Dry and sealed, storage time at 4°C < 14 days
DV200%≥30%
4°C or Room Temperature
*From FFPE section to library prep, try to keep the interval within 14 days as much as possible.
Sequencing Strategy and Turnaround Time
Library Type
Sequencing Strategy
Recommended Data
Species
Turnaround Time (< 4 samples)
10x Visium HD spatial gene expression library
NovaSeq PE150
Coverage Area * 275,000,000 read pairs
~100 Gb/sample
Human or Mouse
WOBI
WBI
28 working days
35 working days
Analysis Contents
Standard Analysis
Software
Data QC
Mapping and Quantification
Space Ranger
Dimensionality Reduction, Clustering, and Differential Analysis Graphclust clustering
K-means clustering
Space Ranger
Seurat Analysis PCA analysis
Spatial variable gene expression analysis Clustering and dimensionality reduction analysis
Seurat
Differential Expression Gene Analysis (DEG) DEGs clustering heatmap
Spatial distribution of DEGs Violin plot
t-SNE and UMAP dimensional reduction visualization
edgeR Seurat
Functional Enrichment Analysis： GO enrichment
KEGG pathway enrichment Reactome enrichment
clusterProfiler
## FAQ
What samples are compatible with Visium HD?
- A: Visium HD is compatible with human and mouse formalin-fixed paraffin-embedded (FFPE) tissue sections containing mRNA. This includes archived FFPE blocks and pre-sectioned tissue on glass slide.
What glass slides are compatible with Visium HD assay?
- A: We recommend utilizing positively charged glass slides within the following dimensions for use with the Visium CytAssist instrument and Visium S3 Cassettes:
A list of glass slide part numbers tested and considerations for use with the Visium HD assay can be found in the Visium HD Spatial Applications Protocol Planner (CG000698).
- What is the capture area for Visium HD?
- A: Visium HD Spatial Gene Expression slides contain two 6.5 x 6.5 mm Capture Areas with a continuous lawn of oligonucleotides arrayed in millions of 2 x 2 µm barcoded squares without gaps, achieving single cell–scale spatial resolution.
Visium HD spatial gene expression tested tissues.
- A: https://www.10xgenomics.com/support/spatial-gene-expression-hd/documentation/steps/tissue-prep/visium-hd-spatial-gene-expression-tested-tissues
What are the recommended sequencing specifications for Visium HD libraries?
- A: For a Visium HD capture area fully covered by tissue (100%), the sequencing recommendation is a minimum of 275 million read pairs. If a capture area is not fully covered by tissue, we recommend either guesstimating capture area coverage and multiplying that percentage by 275 million read pairs or utilizing Loupe Browser Visium HD Manual Alignment Wizard for a more accurate determination (v8.0 or later).
We suggest customer to sequence on NovaSeq PE150 partial lane, please check with APM for availability of lane sequencing.
Read1
i5 index
Read2
I7 index
43 cycles
10 cycles
50 cycles
Visium HD Spatial Gene Expression Reagent Kits User Guide (CG000685)
Spatial Gene Expression for FFPE – Stereo-seq
The FFPE Stereo-seq transcriptome approach is particularly useful for studying complex tissues, such as tumors, where understanding the spatial organization of gene expression can provide insights into cellular heterogeneity, microenvironment interactions, and disease progression. This technology leverages a specialized chip that uses DNBSEQ sequencing to capture spatial gene expression data at an ultra-high resolution, reaching up to 500 nanometers. This means that individual cells within the tissue can be profiled with exceptional precision, enabling the creation of detailed molecular maps that reflect the tissue's original architecture.
## Sample Requirements (Tianjin lab)
Sample Type
Sample Amount
Preservation
Sample QC
Shipping
FFPE block (recommended)
1 block, FFPE block must be contained on plastic dehydrating box, otherwise could not be installed on
the sectioning device
After embedding store at 4°C, protected from light
DV200%≥30%
4-8°C (ice pack) or Room Temperature
FFPE section
10-15 FFPE(5μm thickness) scrolls in 1.5mL tube for sample QC；
4-6 FFPE(5μm thickness) tissue sections,
place each FFPE sections into a new 50 mL centrifuge tubes for library prep
Dry and sealed, storage time at 4°C < 14 days
DV200%≥30%
4-8°C (ice pack) or Room Temperature
*Please refer to “STO-FFPE Sample Preparation and Transportation Guideline” on Wedrive.
Sequencing Strategy and Turnaround Time
Library Type
Chip Size
Sequencing Strategy
Recommended Data
Species
Turnaround Time (<4 samples)
FFPE stereo-seq transcriptome library
1cm x 1cm
DNBSEQ T7 PE75
2500 M reads/sample
No limitation
6 weeks
Analysis Contents
Standard Analysis
Software
Data QC
fqstat
Mapping
STAR
Gene Quantification and Visualization
Bam2Gem StereoMap
Clustering Analysis: cell clustering, and marker gene
Seurat
Differential Expression Gene Analysis (DEGs)
Seurat
Functional Enrichment Analysis： GO enrichment
KEGG pathway enrichment Reactome enrichment
clusterProfiler
## FAQ
Why FFPE Stereo-seq chip can capture both coding and non-coding RNAs?
- A: FFPE Stereo-seq chip use random probe instead of polyA tail primer, which can obtain both coding and non-coding RNAs, even microbial RNAs.
- What is the library structure of FFPE Stereo-seq library?
- A: Sequencing Strategy: DNBSEQ T7 PE75, read1 25bp, read2 59bp.
- Can the library of STOmics Stereo-seq Transcriptomics set be pooled with other libraries for sequencing?
- A: No, Stereo-seq Transcriptomics Set library requires different sequencing protocols and sequencing reagents compared to other libraries.
- How to choose appropriate bin size when analyzing the data?
- A: Some information, such as cell sizes of specific tissue types, can be used. It is recommended to vary the bin level repeatedly based on the results of downstream analyses, with a spectrum of bin20, 50, 100, and 200. Bin20 is about the size of a regular mammalian cell, while bin50 and bin100 are both frequently adopted in the analysis. And bin200 is generally used for immediate visualization of SAW outputs.
Why is ssDNA-stained tissue image used in “image registration” for spatial mapping of transcriptomics data instead of DAPI or H&E staining?
- A: BGI has compared and tested various commercialized staining reagents and found that ssDNA staining has the least effects on the downstream mRNA capture rate. In addition, ssDNA staining allows visualization of track lines on the Stereo-seq Chip N (1cm*1cm).
- What is the BGI data warning standard in SAW analysis report? A: This for is the warning standard from BGI.
Official FFPE Stereo-seq library prep protocol:
- A: Stereo-seq transcriptomics set for FFPE
Stereo-seq Sample Preparation Sectioning and Mounting Guide for Formalin-fixed and Paraffin-embedded (FFPE) Samples on Stereo-seq Chip Slides
What advanced analysis can we provide?
- A: Cellchat analysis, Pseudotime analysis (Trajectory analysis) and cell type annotation analysis, please evaluate case by case.
