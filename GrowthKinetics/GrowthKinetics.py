import sys
import logging
from BuildTree.ClusterObject import Cluster
from BuildTree.Tree import Tree
import data.Patient as Patient
from .GrowthKineticsEngine import GrowthKineticsEngine

from BuildTree.BuildTreeEngine import BuildTreeEngine

sys.path.append('../')

logging.basicConfig(filename='growth_kinetics.log',
                    filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S',
                    level=getattr(logging, "DEBUG"))


# Main run method

def run_tool(args):
    logging.debug('Arguments {}'.format(args))

    # init a Patient
    patient_data = Patient.Patient(indiv_name=args.indiv_id, driver_genes_file=args.driver_genes_file)

    # Patient load cluster and mut ccf files
    parse_sif_file(args.sif, args.mutation_ccf_file, patient_data)
    load_clustering_results(args.cluster_ccf_file, patient_data)

    tree_edges = load_tree_edges_file(args.tree_tsv)
    bt_engine = BuildTreeEngine(patient_data)
    tree = Tree()
    tree.init_tree_from_clustering(patient_data.ClusteringResults)
    tree.set_new_edges(tree_edges)
    patient_data.TopTree = tree

    patient_data.TopTree = bt_engine.top_tree
    patient_data.TreeEnsemble = bt_engine.trees

    gk_engine = GrowthKineticsEngine(patient_data)

    gk_engine.estimate_growth_rate(args.n_iter)

    """
    # Output and visualization
    import output.PhylogicOutput
    phylogicoutput = output.PhylogicOutput.PhylogicOutput()
    phylogicoutput.write_tree_tsv(bt_engine.mcmc_trace, bt_engine.trees_ll, args.indiv_id)
    phylogicoutput.write_constrained_ccf_tsv(constrained_ccf, cell_ancestry, args.indiv_id)
    phylogicoutput.write_cell_abundances_tsv(cell_abundance, cell_ancestry, args.indiv_id)
    phylogicoutput.generate_html_from_tree(args.mutation_ccf_file, args.cluster_ccf_file,
                                           args.indiv_id + '_build_tree_posteriors.tsv',
                                           args.indiv_id + '_constrained_CCF.tsv', sif=args.sif,
                                           drivers=patient_data.driver_genes,
                                           treatment_file=args.treatment_data)
    """


def load_tree_edges_file(tree_tsv):
    reader = open(tree_tsv, 'r')
    header = reader.readline()
    top_tree = reader.readline()
    return eval(top_tree.split('\t')[-1].strip())


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
            cluster_id = mutation.cluster_assignment
            clustering_results[cluster_id].add_mutation(mutation)
            if mutation.var_str not in mutations_nd_hist:
                mutations_nd_hist[mutation.var_str] = []
            mutations_nd_hist[(mutation.var_str, cluster_id)].append(mutation.ccf_1d)
    for (mut_var_str, cluster_id), mutation_nd_hist in mutations_nd_hist.items():
        print mutation_nd_hist
        clustering_results[cluster_id].add_mutation(mut_var_str, mutation_nd_hist)
    patient_data.ClusteringResults = clustering_results
