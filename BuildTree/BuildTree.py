import os
import logging
from .ClusterObject import Cluster

# Remove all handlers associated with the root logger object.
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'build_tree_log.log')
print filename
logging.basicConfig(filename=filename,
                    filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S',
                    level=getattr(logging, "DEBUG"))


# Main run method
def run_tool(args):
    logging.debug('Arguments {}'.format(args))

    import data.Patient as Patient
    from .CellPopulationEngine import CellPopulationEngine
    from .BuildTreeEngine import BuildTreeEngine

    # init a Patient
    patient_data = Patient.Patient(indiv_name=args.indiv_id, driver_genes_file=args.driver_genes_file)

    # Patient load cluster and mut ccf files
    parse_sif_file(args.sif, args.mutation_ccf_file, patient_data)
    load_clustering_results(args.cluster_ccf_file, patient_data)
    patient_data.preprocess_samples()
    # Building Phylogenetic Tree
    bt_engine = BuildTreeEngine(patient_data)
    bt_engine.build_tree(n_iter=args.n_iter)
    # Assign Top tree to Patient
    patient_data.TopTree = bt_engine.top_tree
    patient_data.TreeEnsemble = bt_engine.trees

    # Computing Cell Population
    cp_engine = CellPopulationEngine(patient_data)
    constrained_ccf = cp_engine.compute_constrained_ccf(n_iter=args.n_iter)
    cell_ancestry = bt_engine.get_cell_ancestry()
    cell_abundance = cp_engine.get_cell_abundance(constrained_ccf)
    # Output and visualization
    import output.PhylogicOutput
    phylogicoutput = output.PhylogicOutput.PhylogicOutput()
    phylogicoutput.write_tree_tsv(bt_engine.mcmc_trace, bt_engine.trees_ll, args.indiv_id)
    phylogicoutput.write_constrained_ccf_tsv(constrained_ccf, cell_ancestry, args.indiv_id)
    phylogicoutput.write_cell_abundances_tsv(cell_abundance, cell_ancestry, args.indiv_id)
    phylogicoutput.generate_html_from_tree(args.mutation_ccf_file, args.cluster_ccf_file,
                                           args.indiv_id + '_build_tree_posteriors.tsv',
                                           args.indiv_id + '_constrained_ccf.tsv',
                                           sif=args.sif,
                                           drivers=patient_data.driver_genes,
                                           treatment_file=args.treatment_data,
                                           tumor_sizes_file=args.tumor_size, )
    # cnv_file=args.indiv_id + '.cnvs.txt')


def parse_sif_file(sif_file, mutation_ccf_file, patient_data):
    with open(sif_file, 'r') as reader:
        for line in reader:
            if not line.strip() == "":
                # for now, assume input file order is of the type sample_id\tmaf_fn\tseg_fn\tpurity\ttimepoint
                values = line.strip('\n').split('\t')
                if line.startswith('sample_id'):
                    header = line.strip('\n').split('\t')
                    header = {x: i for i, x in enumerate(header)}
                else:
                    sample_id = values[header['sample_id']]
                    seg_fn = values[header['seg_fn']]
                    purity = float(values[header['purity']])
                    timepoint = float(values[header['timepoint']])
                    logging.debug("Adding sample {}".format(sample_id))

                    patient_data.addSample(mutation_ccf_file, sample_id,
                                           input_type="post-clustering",
                                           timepoint_value=timepoint,
                                           seg_file=seg_fn,
                                           purity=purity)


def load_clustering_results(cluster_info_file, patient_data):
    clustering_results = {}
    ccf_headers = ['postDP_ccf_' + str(i / 100.0) for i in range(0, 101, 1)]
    sample_names = [sample.sample_name for sample in patient_data.sample_list]
    with open(cluster_info_file, 'r') as reader:
        for line in reader:
            values = line.strip('\n').split('\t')
            if line.startswith('Patient_ID'):
                header = dict((item, idx) for idx, item in enumerate(values))
            else:
                sample_id = values[header['Sample_ID']]
                cluster_id = int(values[header['Cluster_ID']])
                ccf = [float(values[header[i]]) for i in ccf_headers]
                if cluster_id not in clustering_results:
                    new_cluster = Cluster(cluster_id, sample_names)
                    clustering_results[cluster_id] = new_cluster
                    logging.debug('Added cluster {} '.format(cluster_id))
                clustering_results[cluster_id].add_sample_density(sample_id, ccf)
    for cluster_id, cluster in clustering_results.items():
        cluster.set_blacklist_status()
        clustering_results[cluster_id] = cluster

    # Create for each cluster dictionary of mutations (key - mut_var_str and value- nd_histogram in log space)
    mutations_nd_hist = {}
    for sample in patient_data.sample_list:
        for mutation in sample.mutations:
            if mutation not in mutations_nd_hist:
                mutations_nd_hist[mutation] = []
            mutations_nd_hist[mutation].append(mutation.ccf_1d)
    for mutation, mutation_nd_hist in mutations_nd_hist.items():
        clustering_results[mutation.cluster_assignment].add_mutation(mutation, mutation_nd_hist)
    patient_data.ClusteringResults = clustering_results
