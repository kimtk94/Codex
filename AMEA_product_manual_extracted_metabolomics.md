# AMEA Product Manual 원문 발췌 (Metabolomics)

- Source: `AMEA Product Manual.docx`
- Method: DOCX XML 텍스트를 추출해 metabolomics 구간만 정리 (요약/해석 최소화)

## Metabolomics Service Overview
- Service Type
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
## Basic Concepts in Metabolomics
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
- Workflow of Untargeted Metabolomics
The workflow of untargeted metabolomics includes sample collection, metabolite extraction, data acquisition, and data processing. Because metabolites are highly dynamic, chemically diverse, and vary widely in concentration, each step - from sample collection and preservation to extraction and detection
- can affect data quality and ultimately influence bioinformatics outcomes. To ensure accuracy and reliability, Novogene implements rigorous quality control across the entire workflow and adheres to standardized metabolomics protocols, delivering consistent, high-quality results. Novogene currently offers two untargeted metabolomics services: Untargeted Metabolomics Plus and Untargeted Metabolomics Pro.
Figure 2 Project workflow for Untargeted Metabolomics
## Sample Requirements and Guidelines
The SG lab can accept the below sample types for Untargeted Metabolomics service.
- Sample type
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
## Data Acquisition in Untargeted Metabolomics Plus and Pro
- Acquisition Parameters
- Service
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
## Summary of Untargeted Metabolomics Plus and Pro
- Service
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
## Key Advantages of Untargeted Metabolomics Plus and Pro
Database: A high-quality secondary spectral database including in-house standard database (18,000+ standards) and in-house secondary spectrum library, ensuring comprehensive and high-quality search results.
Deliverables: High identification accuracy (Level1:1200+);
A significantly increased number of identifications (total exceeding 7,000 compounds);
Bioinformatics Analysis: Comprehensive and diverse analytical points: Delivers 27 standard analytical results, with additional availability of multiple advanced analyses and correlation analysis services.
## Recommended Strategies for Untargeted Metabolomics
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
## Customer Literature and Application Scenarios
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
- What do “mass error” and “score” mean in the raw data file in result files?
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
## Project workflow of Quasi-targeted Metabolomics
The project workflow for Quasi-targeted Metabolomics is similar to Untargeted Metabolomics. For detailed information, please refer to the workflow described in the Untargeted Metabolomics section.
## Sample Collection and Requirements
The sample collection and requirements for Quasi-targeted Metabolomics is similar to Untargeted Metabolomics. For detailed information, please refer to the workflow described in the Untargeted Metabolomics section.
Data Acquisition
- Acquisition Parameters
- Service
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
## In-house Quasi-targeted Metabolomics Database
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
## Number of Level1 Detection
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
## Targeted Metabolomics Products
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
BI Analysis
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
## Comparing Metabolomics Services and Choosing the Right Option
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
Introduction to LC-MSMS8
- What is Proteome?10
- What is Proteomics?10
- What is Label-free or Label-based Quantification in Proteomics?11
The Acquisition Modes of Proteomics12
- What do We Get from Raw Data?13
The Principal of Searching15
The Selection of Database16
Introduction to Quantitative proteomics17
- What is Quantitative Proteomics17
- Workflow of Quantitative Proteomics17
- Sample Requirements and Guidelines18
- Acquisition Parameters in Quantitative Proteomics20
BI Analysis21
Project Experience in Novogene22
Key Advantages of Quantitative Proteomics24
Application for Quantitative Proteomics25
Customer Literature and Application Scenarios25
Case Study26
FAQ29
